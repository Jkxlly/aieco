from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import PromptSession, ForumPost, ForumComment

DARK_INPUT = {'style': 'width:100%;font-family:var(--mono);font-size:14px;padding:10px 13px;background:var(--surface2);border:0.5px solid var(--border);border-radius:9px;color:var(--text);outline:none;transition:border-color .15s;'}
DARK_SELECT = {'style': 'width:100%;font-family:var(--mono);font-size:13.5px;padding:9px 12px;background:var(--surface2);border:0.5px solid var(--border);border-radius:9px;color:var(--text);outline:none;-webkit-appearance:none;'}
DARK_AREA = {'style': 'width:100%;font-family:var(--mono);font-size:14px;padding:13px;background:var(--surface2);border:0.5px solid var(--border);border-radius:10px;color:var(--text);outline:none;resize:vertical;min-height:150px;line-height:1.65;', 'rows': 5}

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={**DARK_INPUT, 'placeholder': 'your@email.com'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'Choose a username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget = forms.PasswordInput(attrs={**DARK_INPUT, 'placeholder': 'Create a password'})
        self.fields['password2'].widget = forms.PasswordInput(attrs={**DARK_INPUT, 'placeholder': 'Confirm password'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class PromptSessionForm(forms.ModelForm):
    class Meta:
        model  = PromptSession
        fields = ['title', 'prompt_text', 'ai_model', 'region', 'notes']
        widgets = {
            'title':       forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'e.g. Draft marketing email'}),
            'prompt_text': forms.Textarea(attrs={**DARK_AREA, 'placeholder': 'Paste your prompt here…', 'id': 'p-text'}),
            'ai_model':    forms.Select(attrs=DARK_SELECT),
            'region':      forms.Select(attrs=DARK_SELECT),
            'notes':       forms.Textarea(attrs={**DARK_INPUT, 'rows': 2, 'placeholder': 'Optional notes…'}),
        }


class ForumPostForm(forms.ModelForm):
    class Meta:
        model  = ForumPost
        fields = ['title', 'body', 'tag']
        widgets = {
            'title': forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'Post title'}),
            'body':  forms.Textarea(attrs={**DARK_AREA, 'placeholder': 'Share your results, questions or insights…', 'rows': 6}),
            'tag':   forms.Select(attrs=DARK_SELECT),
        }


class ForumCommentForm(forms.ModelForm):
    class Meta:
        model  = ForumComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={**DARK_AREA, 'placeholder': 'Write a reply…', 'rows': 3}),
        }
