from django.contrib.auth.models import Permission, User
    
# Classes to override default OIDCAuthenticationBackend (Keycloak authentication)
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

class AADB2CAuthenticationBackend(OIDCAuthenticationBackend):

    def create_user(self, claims):
        """ Overrides Authentication Backend so that Django users are
            created with the keycloak preferred_username.
            If nothing found matching the email, then try the username.
        """
        # print(f"claims::create_user: {claims}")
        # print(super(OIDCAuthenticationBackend, self).__dir__())
        user = super().create_user(claims)
        # Keycloak field names
        user.first_name = claims['given_name']
        user.last_name = claims['family_name']
        user.email = claims['email']
        user.username = claims['preferred_username']

        # allow admin console use
        user.is_staff = True

        # custom admin console permissions to add to everybody in OIDC
        codenames = [
            'add_nfc',
            'change_nfc',
            'delete_nfc',
            'view_nfc',
            'add_nfcterminal',
            'change_nfcterminal',
            'delete_nfcterminal',
            'view_nfcterminal',
            'add_person',
            'change_person',
            'delete_person',
            'view_person',
            'add_personemail',
            'change_personemail',
            'delete_personemail',
            'view_personemail',
            'add_qrcustom',
            'change_qrcustom',
            'delete_qrcustom',
            'view_qrcustom',
            'add_qrcategory',
            'change_qrcategory',
            'delete_qrcategory',
            'view_qrcategory',
            ]

        for codename in codenames:
            permission = Permission.objects.get(codename=codename)
            user.user_permissions.add(permission)

        user.save()
        return user

    def filter_users_by_claims(self, claims):
        """ Return all users matching the specified email.
            If nothing found matching the email, then try the username
        """
        # print(f"claims::filter_user: {claims}")
        email = claims.get('email')
        preferred_username = claims.get('preferred_username')

        if not email:
            return self.UserModel.objects.none()
        users = self.UserModel.objects.filter(email__iexact=email)

        if len(users) < 1:
            if not preferred_username:
                return self.UserModel.objects.none()
            users = self.UserModel.objects.filter(username__iexact=preferred_username)
        return users

    def update_user(self, user, claims):
        # print(f"claims::update_user: {claims}")
        user.first_name = claims['given_name']
        user.last_name = claims['family_name']
        user.email = claims['email']
        user.username = claims['preferred_username']
        user.is_staff = True
        user.save()
        return user
