# This file is part of AI ECO. #
# views.py — all view functions for the AIECO calculator application
# Views receive an HTTP request, process it, and return an HTTP response or redirect
# @login_required decorator redirects unauthenticated users to /login/

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
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
    Passes all five reference tables to the template so dropdowns are populated
    from the database. All calculation logic runs client-side in JavaScript —
    no database write occurs on this page and no authentication is required.
    Hardware_list, operations and precision_types are seeded by seed_data command.
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
    Handles new user registration using the custom RegisterForm.
    On success: password is hashed with PBKDF2-SHA256, user is logged in,
    post_save signal creates user_profile, redirected to dashboard.
    On failure: form re-renders with field-level error messages.
    Authenticated users are redirected to home immediately.
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
    Handles user login using Django built-in AuthenticationForm.
    PBKDF2-SHA256 hash is verified against the stored password hash.
    On success: authenticated session created, redirected to dashboard.
    On failure: form re-renders with generic error (does not reveal which field was wrong).
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
    """
    Logs the user out by destroying the authenticated session.
    Redirects to homepage after logout.
    """
    logout(request)
    return redirect('home')


# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    """
    Personal emissions dashboard for the logged-in user.
    select_related prefetches emissions, ai_model and region in a single SQL query
    to avoid N+1 query patterns when rendering the session list.
    Total CO2 is aggregated at the database layer using Django ORM Sum annotation.
    Budget comparison triggers the warning banner when total exceeds monthly_budget_g.
    """
    # Fetch sessions with related data prefetched in one query
    sessions = PromptSession.objects.filter(
        user=request.user
    ).select_related('emissions', 'ai_model', 'region').order_by('-created_at')

    # Aggregate total CO2 at the database layer — more efficient than summing in Python
    total_co2 = sessions.aggregate(
        total=Sum('emissions__co2_grams')
    )['total'] or 0

    # Read monthly budget from user_profile — None if not set
    budget   = getattr(getattr(request.user, 'profile', None), 'monthly_budget_g', None)
    pct_used = round((total_co2 / budget) * 100, 1) if budget else 0

    # Per-model breakdown — used for the most used model summary card
    model_stats = sessions.values('ai_model__model_name').annotate(
        count=Count('id'),
        total_co2=Sum('emissions__co2_grams')
    ).order_by('-total_co2')

    return render(request, 'calculator/dashboard.html', {
        'sessions':    sessions[:10],   # Last 10 for the recent sessions list
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
    On POST: saves PromptSession, then PromptEmissions.save() runs the
    three-stage calculation pipeline (token estimation -> energy -> CO2).
    On GET: renders blank form with model and region dropdowns.
    Redirects to session detail page after successful save.
    """
    if request.method == 'POST':
        form = PromptSessionForm(request.POST)
        if form.is_valid():
            session      = form.save(commit=False)
            session.user = request.user  # Assign logged-in user before saving
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
    select_related prefetches emissions, ai_model and region in one query.
    Returns empty queryset (not 404) when user has no sessions.
    """
    sessions = PromptSession.objects.filter(
        user=request.user
    ).select_related('emissions', 'ai_model', 'region').order_by('-created_at')
    return render(request, 'calculator/session_list.html', {'sessions': sessions})


@login_required
def session_detail(request, pk):
    """
    Shows a single prompt session with its emissions results.
    get_object_or_404 with user=request.user ensures users can only
    view their own sessions — returns 404 if pk belongs to another user.
    """
    session = get_object_or_404(PromptSession, pk=pk, user=request.user)
    return render(request, 'calculator/session_detail.html', {'session': session})


@login_required
def session_edit(request, pk):
    """
    Allows the user to edit an existing session.
    Saving triggers PromptEmissions.save() which recalculates emissions
    from the updated prompt text, keeping results consistent with stored data.
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
    Deletes a prompt session and its linked emissions record.
    PromptEmissions is removed automatically via CASCADE on the OneToOneField.
    GET: renders confirmation page. POST: performs deletion and redirects.
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
    Annotates each post with comment_count to avoid extra queries in the template.
    """
    selected_tag = request.GET.get('tag', '')
    posts = ForumPost.objects.select_related('user').prefetch_related('comments')
    if selected_tag:
        posts = posts.filter(tag=selected_tag)
    posts = posts.order_by('-created_at')

    # Attach comment count to each post object for use in the template
    for post in posts:
        post.comment_count = post.comments.count()

    tags = getattr(ForumPost, 'TAG_CHOICES', [
        ('results', 'Results'), ('question', 'Question'),
        ('tip', 'Tip'), ('discussion', 'Discussion'),
    ])
    return render(request, 'calculator/forum_list.html', {
        'posts': posts, 'tags': tags, 'selected_tag': selected_tag,
    })


@login_required
def forum_create(request):
    """Creates a new forum post for the logged-in user."""
    if request.method == 'POST':
        form = ForumPostForm(request.POST)
        if form.is_valid():
            post      = form.save(commit=False)
            post.user = request.user
            post.save()
            return redirect('forum_detail', pk=post.pk)
    else:
        form = ForumPostForm()
    return render(request, 'calculator/forum_create.html', {'form': form})


@login_required
def forum_detail(request, pk):
    """
    Shows a single forum post with all its comments.
    Also handles POST for adding a new comment to the post.
    Comments ordered ascending by created_at so threads read chronologically.
    """
    post     = get_object_or_404(ForumPost, pk=pk)
    comments = post.comments.select_related('user').order_by('created_at')
    if request.method == 'POST':
        form = ForumCommentForm(request.POST)
        if form.is_valid():
            comment      = form.save(commit=False)
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
    Server-side proxy to the Anthropic Claude API.
    ANTHROPIC_API_KEY is stored as a Render environment variable and never
    sent to the browser. Uses Claude Haiku to keep API costs minimal.
    Accepts JSON POST with 'message' and 'history' fields.
    Returns JSON with 'reply' field containing the assistant response.
    """
    try:
        body    = json.loads(request.body)
        message = body.get('message', '').strip()
        history = body.get('history', [])

        if not message:
            return JsonResponse({'error': 'No message provided'}, status=400)

        # Read API key from server environment — never hardcode
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return JsonResponse({'reply': (
                'EcoBot is not configured yet. '
                'Please add ANTHROPIC_API_KEY to your Render environment variables.'
            )})

        import urllib.request

        # System prompt defines EcoBot role and AIECO methodology knowledge
        system_prompt = """You are EcoBot, the AI assistant for AIECO (aieco.uk).
Your role:
1. Help users understand their AI carbon emissions results
2. Give practical recommendations to reduce their AI carbon footprint
3. Explain AIECO methodology: Samsi et al. (2023), Guidi et al. (2024)
4. Act as a helpful general AI assistant

Key facts:
- Token count = word count x 1.33
- Energy = tokens x model Wh/token (Samsi et al. 2023)
- CO2 = energy x regional carbon intensity (Guidi et al. 2024)
- Carbon intensity varies up to 20x by region
- INT8 precision uses approximately 65% less energy than FP32

Keep responses concise, friendly and practical."""

        # Build message list from last 8 turns of conversation history
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

        # Make API request using stdlib urllib — no extra dependencies required
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key':         api_key,
                'anthropic-version': '2023-06-01',
                'content-type':      'application/json',
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        # Extract text content from first content block
        reply = data['content'][0]['text']
        return JsonResponse({'reply': reply})

    except Exception:
        # Return safe fallback — never expose error details to the browser
        return JsonResponse({'reply': 'Something went wrong. Please try again.'})
