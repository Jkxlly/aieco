# views.py — all view functions for the AIECO calculator application
# Each view handles HTTP requests and returns an HTTP response or redirect

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from .models import (
    AIModel, CarbonRegion, HardwareSpec, OperationType,
    PrecisionType, PromptSession, PromptEmissions,
    ForumPost, ForumComment
)
from .forms import RegisterForm, PromptSessionForm, ForumPostForm, ForumCommentForm
import json
import os


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
@require_POST
@csrf_protect
def chat_api(request):
    """
    Proxies chat messages to the Anthropic Claude API.
    The API key is stored as a server-side environment variable (ANTHROPIC_API_KEY)
    and never exposed to the browser. Uses Claude Haiku to minimise API cost.
    Returns a JSON response with the assistant's reply.
    """
    try:
        body    = json.loads(request.body)
        message = body.get('message', '').strip()
        history = body.get('history', [])

        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return JsonResponse({'reply': (
                'EcoBot is not configured yet. '
                'Please add ANTHROPIC_API_KEY to your Render environment variables.'
            )})

        import urllib.request

        # System prompt defines EcoBot's role and knowledge about AIECO methodology
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

        # Build message history for the API request (last 8 turns for context window)
        messages_list = []
        for h in history[:-1]:
            if h.get('role') in ('user', 'assistant'):
                messages_list.append({'role': h['role'], 'content': h['content']})
        messages_list.append({'role': 'user', 'content': message})

        payload = json.dumps({
            'model':      'claude-haiku-4-5-20251001',
            'max_tokens': 600,
            'system':     system_prompt,
            'messages':   messages_list,
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key':          api_key,
                'anthropic-version':  '2023-06-01',
                'content-type':       'application/json',
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        reply = data['content'][0]['text']
        return JsonResponse({'reply': reply})

    except Exception:
        return JsonResponse({'reply': 'Something went wrong. Please try again.'})
