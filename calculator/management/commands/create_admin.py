from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = "Create admin user from environment variables"

    def handle(self, *args, **kwargs):
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD')
        email    = os.environ.get('ADMIN_EMAIL', 'james@aieco.uk')

        if not password:
            self.stdout.write(self.style.WARNING('ADMIN_PASSWORD not set — skipping'))
            return

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'Admin user {username} created'))
        else:
            self.stdout.write(f'Admin {username} already exists')