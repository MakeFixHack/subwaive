from django.contrib.auth.models import Group

# Classes to override default OIDCAuthenticationBackend (Keycloak authentication)
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

class AADB2CAuthenticationBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        """ Overrides Authentication Backend so that Django users are
            created with the keycloak preferred_username.
            If nothing found matching the email, then try the username.
        """
        print(f"create_user::claims: {claims}")
        print(f"create_user::claims.get('groups',[]): {claims.get('groups',[])}")

        user = super().create_user(claims)
        # Keycloak field names
        user.first_name = claims['given_name']
        user.last_name = claims['family_name']
        user.email = claims['email']
        user.username = claims['preferred_username']

        keycloak_roles = claims.get('groups',[])

        # allow admin console use if a role is defined for the user
        if keycloak_roles:
            user.is_staff = True
    
        user.save()
        
        # add new user to groups defined by OIDC provider
        for r in keycloak_roles:
            group,was_created = Group.objects.get_or_create(name=r)
            print(f"create_user: Group '{group}' was created? {was_created}")
            group.user_set.add(user)

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
        #!!! when does this run?
        #!!! update group membership

        print(f"update_user::claims: {claims}")
        user.first_name = claims['given_name']
        user.last_name = claims['family_name']
        user.email = claims['email']
        user.username = claims['preferred_username']
        #!!! condition on being a member of a group
        user.is_staff = True
        #else: user.is_staff = False
        user.save()
        return user
    