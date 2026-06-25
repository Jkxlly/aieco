# urls.py — URL routing for the calculator app
# Maps URL patterns to view functions defined in views.py

from django.urls import path
from . import views

urlpatterns = [
    # Homepage — hardware calculator (client-side, no auth required)
    path('',                          views.home,            name='home'),

    # Authentication
    path('register/',                 views.register_view,   name='register'),
    path('login/',                    views.login_view,       name='login'),
    path('logout/',                   views.logout_view,      name='logout'),

    # Methodology — public, transparent documentation of every assumption
    path('methodology/',              views.methodology_view, name='methodology'),

    # Open data — CC-BY dataset landing page + downloads
    path('data/',                     views.open_data,        name='open_data'),
    path('data/<str:table>.<str:fmt>', views.data_download,   name='data_download'),

    # Personal dashboard — aggregates monthly emissions data
    path('dashboard/',                views.dashboard,        name='dashboard'),

    # Prompt calculator — saves session to PostgreSQL via PromptEmissions.save()
    path('calculate/',                views.calculate,        name='calculate'),

    # Session history and detail views
    path('sessions/',                 views.session_list,     name='session_list'),
    path('sessions/<int:pk>/',        views.session_detail,   name='session_detail'),
    path('sessions/<int:pk>/edit/',   views.session_edit,     name='session_edit'),
    path('sessions/<int:pk>/delete/', views.session_delete,   name='session_delete'),

    # Community forum
    path('forum/',                    views.forum_list,       name='forum_list'),
    path('forum/new/',                views.forum_create,     name='forum_create'),
    path('forum/<int:pk>/',           views.forum_detail,     name='forum_detail'),

    # EcoBot chat API — proxies to Google Gemini, keeps API key server-side
    path('api/chat/',                 views.chat_api,         name='chat_api'),

    # Hardware calculator API — runs the formula server-side so it is not
    # exposed in browser JavaScript
    path('api/hw-calculate/',         views.hw_calculate,     name='hw_calculate'),
]
