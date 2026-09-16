from django.core.management.base import BaseCommand

from apps.users.roles import sync_roles


class Command(BaseCommand):
    help = "Rebuild the role groups so they match apps/users/roles.py."

    def handle(self, *args, **options):
        self.stdout.write("Syncing role groups...")
        sync_roles(verbose=True)
        self.stdout.write(self.style.SUCCESS("Role groups are in sync."))
