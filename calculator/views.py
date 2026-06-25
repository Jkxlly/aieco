# views.py — all view functions for the AIECO calculator application
# Each view handles HTTP requests and returns an HTTP response or redirect

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.db.models import Sum, Count
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from .models import (
    AIModel, CarbonRegion, HardwareSpec, OperationType,
    PrecisionType, PromptSession, PromptEmissions,
    ForumPost, ForumComment
)
from .forms import RegisterForm, PromptSessionForm, ForumPostForm, ForumCommentForm
from . import methodology as method
import json
import os
import csv


# ── Homepage ──────────────────────────────────────────────────────────────────
def home(request):
    """
    Renders the homepage hardware calculator.
    All reference table data is passed to the template so dropdown options
    are populated from the database rather than hardcoded in HTML.
    The actual calculation is performed client-side in JavaScript (hwCalculate).
    No database write occurs on this page.
    """
    return render(request, 'calculator/home.html', {
        'ai_models':       AIModel.objects.all().order_by('provider', 'model_name'),
        'regions':         CarbonRegion.objects.all().order_by('carbon_intensity_kg_kwh'),
        'hardware_list':   HardwareSpec.objects.all().order_by('manufacturer', 'name'),
        'operations':      OperationType.objects.all().order_by('energy_mult'),
        'precision_types': PrecisionType.objects.all().order_by('energy_factor'),
    })


# ── Hardware calculator API ─────────────────────────────────────────────────
# The hardware calculator's formula and constants used to live in browser
# JavaScript (home.html), which exposed the whole algorithm to anyone viewing
# source. The computation now runs here, server-side: the browser sends only
# the selected row ids, this view looks the reference values up from the
# database and returns finished numbers. The formula never reaches the client.

# Constants specific to the hardware calculator. Kept here (not in the template)
# so they are not shipped to the browser.
HW_PUE = 1.4  # IEA global-average data-centre overhead for the hardware model

# Real-world equivalence factors (kg CO2 or kWh per unit) with their sources.
EQUIV_CO2_PER_CAR_KM   = 0.21      # DEFRA 2024, petrol car
WH_PER_PHONE_CHARGE    = 8.22      # average Li-ion phone battery
CO2_PER_FLIGHT_KG      = 990.0     # ICAO, LHR–JFK return
CO2_PER_TREE_YEAR_KG   = 21.0      # Nowak & Crane 2002
KWH_PER_HOME_DAY       = 10.7      # Ofgem household average
CO2_PER_SEARCH_KG      = 0.0002    # Google Environmental Report 2023


@require_POST
@csrf_exempt
def hw_calculate(request):
    """
    Server-side hardware energy/carbon calculation.

    Accepts a JSON body of selected row ids plus the GPU count and duration,
    resolves the reference values from the database, runs the energy → CO2 →
    cost pipeline in Python and returns the finished figures. Read-only: no
    database writes and no auth, so csrf_exempt is safe here.
    """
    try:
        body = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    try:
        hardware  = get_object_or_404(HardwareSpec,   pk=body.get('hardware_id'))
        operation = get_object_or_404(OperationType,  pk=body.get('operation_id'))
        precision = get_object_or_404(PrecisionType,  pk=body.get('precision_id'))
        region    = get_object_or_404(CarbonRegion,   pk=body.get('region_id'))
    except Exception:
        return JsonResponse({'error': 'Unknown selection'}, status=400)

    # Clamp user-controlled numerics to the same ranges the UI allows.
    try:
        gpus  = max(1, min(512, int(float(body.get('gpus', 1)))))
        hours = max(0.1, float(body.get('hours', 1)))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid GPU count or duration'}, status=400)

    tdp         = float(hardware.tdp_watts)
    op_mult     = float(operation.energy_mult)
    prec_factor = float(precision.energy_factor)
    ci          = float(region.carbon_intensity_kg_kwh)

    # energy_kwh = (TDP × GPUs × op multiplier × precision factor × PUE × hours) / 1000
    energy_kwh = (tdp * gpus * op_mult * prec_factor * HW_PUE * hours) / 1000.0
    co2_kg     = energy_kwh * ci
    co2_g      = co2_kg * 1000.0
    cost_gbp   = energy_kwh * method.ELECTRICITY_PRICE_GBP_PER_KWH

    equivalents = {
        'car_km':    co2_kg / EQUIV_CO2_PER_CAR_KM,
        'phones':    round((energy_kwh * 1000) / WH_PER_PHONE_CHARGE),
        'flights':   co2_kg / CO2_PER_FLIGHT_KG,
        'trees':     co2_kg / CO2_PER_TREE_YEAR_KG,
        'home_days': energy_kwh / KWH_PER_HOME_DAY,
        'searches':  round(co2_kg / CO2_PER_SEARCH_KG),
    }

    recommendations = []
    if ci > 0.3:
        recommendations.append('Switch to a lower-carbon region (France or Norway) to cut emissions by up to 16x')
    if prec_factor > 0.35:
        recommendations.append('Use INT8 precision — reduces energy by approximately 65% with minimal quality loss')
    if 'H100' not in hardware.name:
        recommendations.append('Consider NVIDIA H100 SXM5 — approximately 71% lower operational carbon vs V100')
    if op_mult >= 3.2:
        recommendations.append('Training is 3.2x more energy intensive than inference — consider pre-trained models')

    return JsonResponse({
        'energy_kwh':      energy_kwh,
        'co2_kg':          co2_kg,
        'co2_g':           co2_g,
        'cost_gbp':        cost_gbp,
        'equivalents':     equivalents,
        'recommendations': recommendations,
        'subtitle':        f'{hardware.name} x {gpus} · {hours}h · {region.region_name}',
    })


# ── Methodology ─────────────────────────────────────────────────────────────
def methodology_view(request):
    """
    Public methodology page. Renders every assumption, formula and data source
    used by the calculator, generated from the same constants module and the
    same database tables the calculator actually uses — so it can never drift
    out of sync with the real computation. This transparency is what makes the
    estimates defensible to reviewers and funders.
    """
    # Worked example so readers can follow the numbers end to end.
    example = method.estimate_emissions(
        word_count              = 100,
        wh_per_token            = 0.0000030,   # a mid-range model
        carbon_intensity_kg_kwh = 0.207,       # UK grid
    )
    return render(request, 'calculator/methodology.html', {
        'tokens_per_word':    method.TOKENS_PER_WORD,
        'input_energy_weight':method.INPUT_ENERGY_WEIGHT,
        'output_ratio':       method.DEFAULT_OUTPUT_RATIO,
        'pue':                method.DEFAULT_PUE,
        'price':              method.ELECTRICITY_PRICE_GBP_PER_KWH,
        'uncertainty':        method.UNCERTAINTY_COMPONENTS,
        'combined_uncertainty': round(method.combined_relative_uncertainty() * 100, 1),
        'example':            example,
        'models':             AIModel.objects.all().order_by('provider', 'model_name'),
        'regions':            CarbonRegion.objects.all().order_by('carbon_intensity_kg_kwh'),
        'hardware':           HardwareSpec.objects.all().order_by('manufacturer', 'name'),
        'operations':         OperationType.objects.all().order_by('energy_mult'),
        'precision':          PrecisionType.objects.all().order_by('energy_factor'),
    })


# ── Open data export ──────────────────────────────────────────────────────────
# Field sets exported for each reference table. Keeping this declarative means
# the data page, CSV export and JSON export all stay consistent automatically.
DATA_TABLES = {
    'regions': {
        'label':  'Carbon intensity by region',
        'model':  CarbonRegion,
        'fields': ['region_name', 'region_code', 'country_code',
                   'carbon_intensity_kg_kwh', 'year_recorded', 'source'],
        'order':  'carbon_intensity_kg_kwh',
    },
    'hardware': {
        'label':  'Hardware power specifications',
        'model':  HardwareSpec,
        'fields': ['name', 'manufacturer', 'hardware_type', 'tdp_watts',
                   'fp16_tflops', 'int8_tflops', 'memory_gb',
                   'embodied_co2_kg', 'released_year'],
        'order':  'name',
    },
    'models': {
        'label':  'AI model energy figures',
        'model':  AIModel,
        'fields': ['model_name', 'provider', 'wh_per_token', 'context_window',
                   'params_billions', 'training_co2_kg', 'model_type', 'released_year'],
        'order':  'model_name',
    },
    'operations': {
        'label':  'Operation energy multipliers',
        'model':  OperationType,
        'fields': ['name', 'slug', 'energy_mult', 'description'],
        'order':  'energy_mult',
    },
    'precision': {
        'label':  'Numeric precision energy factors',
        'model':  PrecisionType,
        'fields': ['name', 'slug', 'energy_factor', 'description'],
        'order':  'energy_factor',
    },
}


def open_data(request):
    """Landing page describing the open dataset, its licence and downloads."""
    tables = [{'key': k, 'label': v['label'], 'count': v['model'].objects.count(),
               'fields': v['fields']} for k, v in DATA_TABLES.items()]
    return render(request, 'calculator/open_data.html', {'tables': tables})


def data_download(request, table, fmt):
    """
    Streams a reference table as CSV or JSON. Open data, CC-BY-4.0 — citable and
    reusable by researchers and other tools. No auth required by design.
    """
    spec = DATA_TABLES.get(table)
    if spec is None:
        return JsonResponse({'error': 'Unknown table'}, status=404)

    rows = spec['model'].objects.all().order_by(spec['order'])
    fields = spec['fields']

    if fmt == 'json':
        payload = {
            'dataset':  spec['label'],
            'source':   'AIECO — aieco.uk',
            'licence':  'CC-BY-4.0',
            'fields':   fields,
            'records':  [{f: getattr(r, f) for f in fields} for r in rows],
        }
        resp = JsonResponse(payload, json_dumps_params={'indent': 2})
        resp['Content-Disposition'] = f'attachment; filename="aieco_{table}.json"'
        return resp

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="aieco_{table}.csv"'
        writer = csv.writer(resp)
        writer.writerow(fields)
        for r in rows:
            writer.writerow([getattr(r, f) for f in fields])
        return resp

    return JsonResponse({'error': 'Format must be csv or json'}, status=400)


# ── Authentication ────────────────────────────────────────────────────────────
def register_view(request):
    """
    Handles new user registration.
    On successful registration, the user is automatically logged in and
    redirected to the dashboard. A UserProfile is created via post_save signal.
    """
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'calculator/register.html', {'form': form})


def login_view(request):
    """
    Handles user login using Django's built-in AuthenticationForm.
    Passwords are verified against the PBKDF2-SHA256 hash stored in the database.
    """
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'calculator/login.html', {'form': form})


def logout_view(request):
    """Logs the user out and redirects to the homepage."""
    logout(request)
    return redirect('home')


# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    """
    Personal emissions dashboard for the logged-in user.
    Aggregates total CO2 from all prompt_emissions records using ORM annotation.
    Compares total against user_profile.monthly_budget_g to trigger budget warning.
    Uses select_related to avoid N+1 queries when rendering session list.
    """
    sessions = PromptSession.objects.filter(
        user=request.user
    ).select_related('emissions', 'ai_model', 'region').order_by('-created_at')

    # Aggregate total CO2 for the month — pushed to database layer via annotate
    total_co2 = sessions.aggregate(
        total=Sum('emissions__co2_grams')
    )['total'] or 0

    budget   = request.user.profile.monthly_budget_g if hasattr(request.user, 'profile') else None
    pct_used = round((total_co2 / budget) * 100, 1) if budget else 0

    # Per-model breakdown for comparison chart
    model_stats = sessions.values('ai_model__model_name').annotate(
        count=Count('id'),
        total_co2=Sum('emissions__co2_grams')
    ).order_by('-total_co2')

    return render(request, 'calculator/dashboard.html', {
        'sessions':    sessions[:10],
        'total_co2':   total_co2,
        'budget':      budget,
        'pct_used':    pct_used,
        'model_stats': model_stats,
        'over_budget': total_co2 > budget if budget else False,
    })


# ── Prompt Calculator ─────────────────────────────────────────────────────────
@login_required
def calculate(request):
    """
    Prompt-based carbon calculator.
    On POST, saves a PromptSession to the database. The linked PromptEmissions
    record is created automatically by PromptEmissions.save() which runs the
    three-stage token estimation -> energy -> CO2 pipeline.
    """
    if request.method == 'POST':
        form = PromptSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.user = request.user
            session.save()
            PromptEmissions.objects.create(session=session)
            return redirect('session_detail', pk=session.pk)
    else:
        form = PromptSessionForm()
    return render(request, 'calculator/calculate.html', {'form': form})


# ── Session Views ─────────────────────────────────────────────────────────────
@login_required
def session_list(request):
    """
    Lists all prompt sessions for the logged-in user, ordered newest first.
    Uses select_related to prefetch emissions, ai_model and region in one query.
    """
    sessions = PromptSession.objects.filter(
        user=request.user
    ).select_related('emissions', 'ai_model', 'region').order_by('-created_at')
    return render(request, 'calculator/session_list.html', {'sessions': sessions})


@login_required
def session_detail(request, pk):
    """
    Shows a single prompt session with its calculated emissions results.
    get_object_or_404 ensures users can only view their own sessions.
    """
    session = get_object_or_404(PromptSession, pk=pk, user=request.user)
    return render(request, 'calculator/session_detail.html', {'session': session})


@login_required
def session_edit(request, pk):
    """
    Allows the user to edit the title, prompt text or notes of a saved session.
    Saving triggers PromptEmissions.save() which recalculates emissions from the new prompt text.
    """
    session = get_object_or_404(PromptSession, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PromptSessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            try:
                session.emissions.save()
            except PromptEmissions.DoesNotExist:
                PromptEmissions.objects.create(session=session)
            return redirect('session_detail', pk=session.pk)
    else:
        form = PromptSessionForm(instance=session)
    return render(request, 'calculator/calculate.html', {'form': form, 'editing': True})


@login_required
def session_delete(request, pk):
    """
    Deletes a prompt session and its linked prompt_emissions record.
    The emissions record is removed automatically via CASCADE on the OneToOneField.
    """
    session = get_object_or_404(PromptSession, pk=pk, user=request.user)
    if request.method == 'POST':
        session.delete()
        return redirect('session_list')
    return render(request, 'calculator/session_confirm_delete.html', {'session': session})


# ── Forum Views ───────────────────────────────────────────────────────────────
@login_required
def forum_list(request):
    """
    Lists all forum posts, optionally filtered by tag query parameter.
    Tags: results, question, tip, discussion.
    """
    selected_tag = request.GET.get('tag', '')
    posts = ForumPost.objects.select_related('user').prefetch_related('comments')
    if selected_tag:
        posts = posts.filter(tag=selected_tag)
    posts = posts.order_by('-created_at')

    # Annotate comment count for display without extra queries
    for post in posts:
        post.comment_count = post.comments.count()

    tags = ForumPost.TAG_CHOICES if hasattr(ForumPost, 'TAG_CHOICES') else [
        ('results', 'Results'), ('question', 'Question'),
        ('tip', 'Tip'), ('discussion', 'Discussion'),
    ]
    return render(request, 'calculator/forum_list.html', {
        'posts': posts, 'tags': tags, 'selected_tag': selected_tag,
    })


@login_required
def forum_create(request):
    """Creates a new forum post for the logged-in user."""
    if request.method == 'POST':
        form = ForumPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            return redirect('forum_detail', pk=post.pk)
    else:
        form = ForumPostForm()
    return render(request, 'calculator/forum_create.html', {'form': form})


@login_required
def forum_detail(request, pk):
    """Shows a single forum post with all its comments."""
    post = get_object_or_404(ForumPost, pk=pk)
    comments = post.comments.select_related('user').order_by('created_at')
    if request.method == 'POST':
        form = ForumCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.user = request.user
            comment.save()
            return redirect('forum_detail', pk=pk)
    else:
        form = ForumCommentForm()
    return render(request, 'calculator/forum_detail.html', {
        'post': post, 'comments': comments, 'form': form,
    })


# ── EcoBot Chat API ───────────────────────────────────────────────────────────
# Abuse controls for the public, unauthenticated Gemini proxy. Without these
# anyone could hammer the endpoint and burn the API quota or use it as a free
# LLM relay. The rate limit uses Django's cache; with the default per-process
# cache it is approximate across multiple workers but still bounds abuse.
CHAT_RATE_LIMIT      = 15     # max requests
CHAT_RATE_WINDOW_SEC = 60     # per this many seconds, per client IP
CHAT_MAX_MESSAGE_LEN = 4000   # reject prompts longer than this


def _client_ip(request):
    """Best-effort client IP, honouring the proxy header set by Render/Railway."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _chat_rate_limited(request):
    """Fixed-window per-IP counter; returns True once the limit is exceeded.

    cache.add only writes when the key is absent, which starts a fresh window
    and fixes its expiry; subsequent hits in that window use incr so the window
    does not slide. incr raising means the key expired between calls — treat
    that as the first hit of a new window.
    """
    key = f'chat_rate:{_client_ip(request)}'
    if cache.add(key, 1, timeout=CHAT_RATE_WINDOW_SEC):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=CHAT_RATE_WINDOW_SEC)
            count = 1
    return count > CHAT_RATE_LIMIT


@csrf_exempt
@require_POST
def chat_api(request):
    """
    Proxies chat messages to the Google Gemini API using gemini-2.5-flash.
    The API key is stored as a server-side environment variable (GEMINI_API_KEY)
    and never exposed to the browser. Gemini free tier used.
    Returns a JSON response with the assistant's reply.
    """
    try:
        if _chat_rate_limited(request):
            return JsonResponse({'reply': (
                "You're sending messages a little fast — please wait a minute "
                "and try again."
            )}, status=429)

        body    = json.loads(request.body)
        message = body.get('message', '').strip()
        history = body.get('history', [])

        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        if len(message) > CHAT_MAX_MESSAGE_LEN:
            return JsonResponse({'reply': (
                "That message is too long for EcoBot — please shorten it and "
                "try again."
            )}, status=400)

        api_key = os.environ.get('GEMINI_API_KEY', '')

        if not api_key:
            return JsonResponse({'reply': (
                'EcoBot is not configured yet. '
                'Please add GEMINI_API_KEY to your Render environment variables.'
            )})

        import urllib.request
        import urllib.error
        import logging
        logger = logging.getLogger(__name__)

        system_prompt = """You are EcoBot, the AI assistant for AIECO (aieco.uk).

Your role:
1. Help users understand their AI carbon emissions results from the AIECO calculator
2. Give practical recommendations to reduce their AI carbon footprint
3. Answer questions about AI energy consumption, carbon intensity and sustainability
4. Explain AIECO methodology: Samsi et al. (2023), Guidi et al. (2024), Faiz et al. (2024)
5. Act as a helpful general AI assistant for any other questions

Key methodology facts:
- Token count = word count x 1.33
- Energy = tokens x model Wh/token (Samsi et al. 2023)
- CO2 = energy x regional carbon intensity (Guidi et al. 2024)
- Carbon intensity varies up to 16x by region (Norway 0.017 vs South Africa 0.928 kg/kWh)
- GPT-4 uses approximately 12.5x more energy per token than Claude Haiku
- INT8 precision uses approximately 65% less energy than FP32

Top recommendations to reduce footprint:
- Use smaller models for simple tasks (Claude Haiku, Mistral 7B)
- Choose lower-carbon regions (France, Norway, Sweden)
- Use INT8 precision where quality allows
- Check live UK carbon intensity at carbonintensity.org.uk

Keep responses concise, friendly and practical."""

        # Build full prompt combining system prompt, history and current message
        full_prompt = system_prompt + '\n\n'
        for h in history[:-1]:
            if h.get('role') == 'user':
                full_prompt += 'User: ' + h['content'] + '\n'
            elif h.get('role') == 'assistant':
                full_prompt += 'EcoBot: ' + h['content'] + '\n'
        full_prompt += 'User: ' + message

        payload = json.dumps({
            'contents': [{'parts': [{'text': full_prompt}]}],
            'generationConfig': {'maxOutputTokens': 600}
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
            data=payload,
            headers={
                'Content-Type':  'application/json',
                'x-goog-api-key': api_key,
            },
            method='POST'
        )

        import time
        data = None
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                break
            except urllib.error.HTTPError as http_err:
                body = http_err.read().decode('utf-8', errors='replace')
                logger.error('Gemini HTTP %s (attempt %s): %s', http_err.code, attempt + 1, body)
                last_err = http_err
                if http_err.code in (500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if http_err.code == 429:
                    return JsonResponse({'reply': (
                        "EcoBot is taking a quick break — the AI service is busy "
                        "or has hit its daily limit. Please try again in a few minutes."
                    )})
                if http_err.code in (500, 502, 503, 504):
                    return JsonResponse({'reply': (
                        "EcoBot is temporarily unavailable — the AI service is "
                        "experiencing high demand. Please try again in a moment."
                    )})
                return JsonResponse({'reply': (
                    "EcoBot couldn't reach the AI service right now. "
                    "Please try again shortly."
                )})

        if data is None:
            logger.error('Gemini no data after retries: %s', last_err)
            return JsonResponse({'reply': (
                "EcoBot is temporarily unavailable. Please try again in a moment."
            )})

        reply = data['candidates'][0]['content']['parts'][0]['text']
        return JsonResponse({'reply': reply})

    except Exception:
        logger.exception('EcoBot unexpected error')
        return JsonResponse({'reply': (
            "EcoBot ran into an unexpected error. Please try again shortly."
        )})