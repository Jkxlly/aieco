# This file is part of AI ECO. #
# urls.py — URL routing for the calculator Django app
# Maps URL patterns to view functions defined in views.py
# URL names allow templates to use {% url 'name' %} instead of hardcoded paths

from django.urls import path
from . import views

urlpatterns = [

    # Homepage — hardware calculator (client-side JavaScript, no auth required)
    path('', views.home, name='home'),

    # Authentication — registration, login and logout
    path('register/', views.register_view, name='register'),
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),

    # Personal dashboard — aggregates monthly emissions, requires login
    path('dashboard/', views.dashboard, name='dashboard'),

    # Prompt calculator — saves session to PostgreSQL, requires login
    path('calculate/', views.calculate, name='calculate'),

    # Session management — list, detail, edit and delete
    # <int:pk> captures the session primary key from the URL
    path('sessions/',                 views.session_list,   name='session_list'),
    path('sessions/<int:pk>/',        views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/edit/',   views.session_edit,   name='session_edit'),
    path('sessions/<int:pk>/delete/', views.session_delete, name='session_delete'),

    # Community forum — list, create and detail
    path('forum/',          views.forum_list,   name='forum_list'),
    path('forum/new/',      views.forum_create, name='forum_create'),
    path('forum/<int:pk>/', views.forum_detail, name='forum_detail'),

    # EcoBot chat API — proxies to Anthropic Claude, keeps API key server-side
    path('api/chat/', views.chat_api, name='chat_api'),
]
