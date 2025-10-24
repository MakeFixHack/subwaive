from django.core.management.base import BaseCommand

import logging
import os

from django.contrib.auth.models import Permission, Group
	
from subwaive.models import Log

class Command(BaseCommand):
	def handle(self, *args, **options):
		for g in Group.objects.all():
			permissions_key = f'DJANGO_GROUP_PERMISSION_{g.name.upper().replace("-","_")}'
			print(f"Setting permissions for '{g.name}' from '{permissions_key}' in .env")
			group_perm_list = os.environ.get(permissions_key,'').split(',')
			# print(f'set_group_permissions_from_env::group_perm_list: {group_perm_list}')
			
			if group_perm_list == ['*']: # shorthand for admin users
				# print("set_group_permissions_from_env using all permissions")
				group_perm_list = [x.codename for x in Permission.objects.all()]
			# else:
			#	 print("set_group_permissions_from_env using subset of permissions")

			for p in group_perm_list:
				# print(f'set_group_permissions_from_env::p: {p}')
				perm_qs = Permission.objects.filter(codename=p)
				if perm_qs:
					perm = perm_qs.first()
					# print(perm)
					if not perm in g.permissions.all():
						print(f"Adding '{p}'")
						g.permissions.add(perm)
						Log.new(logging_level=logging.CRITICAL, description='Added permission to group', json={'group': g.name, 'permission': p})
				else:
					Log.new(logging_level=logging.CRITICAL, description='Failed to add permission to group', json={'group': g.name, 'permission': p})
			