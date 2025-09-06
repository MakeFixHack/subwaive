from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import path

from mozilla_django_oidc import views as oidc_views

from subwaive import docuseal
from subwaive import stripe
from subwaive import nfc
from subwaive import person
from subwaive import event
from subwaive import link
from subwaive import logs

from subwaive.settings import IS_USE_OIDC_LOGIN

# Admin
urlpatterns = [
    path('admin/', admin.site.urls),
]

# OIDC login
if IS_USE_OIDC_LOGIN:
    urlpatterns.extend([
        path('login/', LoginView.as_view(redirect_authenticated_user = True, template_name = 'subwaive/login.html'), name = 'login'),
        path("sso/authenticate/", oidc_views.OIDCAuthenticationRequestView.as_view(), name="oidc_authentication_init"),
        path("sso/callback/", oidc_views.OIDCAuthenticationCallbackView.as_view(), name="oidc_authentication_callback"),
    ])

# Event
urlpatterns.extend([
    path('event/list/', event.event_list, name='event_list'),
    path('event/list/<timeframe>/', event.event_list, name='event_list'),
    path('event/refresh/', event.event_refresh_page, name='event_refresh'),
    path('event/refresh/all/', event.refresh_event, name='refresh_event'),
    path('event/refresh/by-token/', event.refresh_event_by_token, name='refresh_event_by_token'),
    path('event/<int:event_id>/', event.event_details, name='event_details'),
    path('person/<int:person_id>/check-in/<int:event_id>/delete/', event.delete_member_check_in, name='delete_member_check_in'),
    path('person/<int:person_id>/event/<int:event_id>/check-in/', event.member_check_in, name='member_check_in'),
    path('person/<int:person_id>/event/<int:event_id>/check-in/force/', event.force_member_check_in, name='force_member_check_in'),
    path('person/<int:person_id>/check-in/remediate/', event.check_in_remediation, name='check_in_remediation'),
])

# Link
urlpatterns.extend([
    path('', link.public_link_list),
    path('links/public/', link.public_link_list, name='public_link_list'),
    path('links/internal/', link.sensitive_link_list, name='sensitive_link_list'),
])

# NFC
urlpatterns.extend([
    path('nfc/check-in/', nfc.nfc_self_serve, name="nfc_self_serve"),
    path('nfc/register/<nfc_id>/', nfc.register_nfc, name="register_nfc"),
    path('nfc/activate/<activation_id>/', nfc.activate_nfc, name="activate_nfc"),
])

# Person
urlpatterns.extend([
    path('email/<int:email_id>/unmerge/', person.unmerge_people, name='unmerge_people'),
    path('email/<int:email_id>/prefer/', person.set_preferred_email, name='set_preferred_email'),
    path('person/search/', person.person_search, name='person_search'),
    path('person/all/', person.person_list, name='person_list'),
    path('person/members/', person.member_list, name='member_list'),
    path('person/members/email/', person.member_email_list, name='member_email_list'),
    path('person/<int:person_id>/', person.person_card, name='person_card'),
    path('person/<int:person_id>/docuseal/', person.person_docuseal, name='person_docuseal'),
    path('person/<int:person_id>/edit/', person.person_edit, name='person_edit'),
    path('person/<int:person_id>/name/<int:important_field_id>/docuseal/', person.set_docuseal_name, name='set_docuseal_name'),
    path('person/<int:person_id>/name/<customer_id>/stripe/', person.set_stripe_name, name='set_stripe_name'),
    path('person/<int:merge_child_id>/merge/', person.merge_people, name='merge_people'),
    path('person/<int:merge_child_id>/merge/<int:merge_parent_id>/', person.merge_people, name='merge_people'),
    path('person/<int:person_id>/stripe/', person.person_stripe, name='person_stripe'),
])

# Logs
urlpatterns.extend([
    path('logs/thin-by-token/', logs.thin_logs_by_token, name='thin_logs_by_token'),
])

# Docuseal
urlpatterns.extend([
    path('docuseal/links/', docuseal.qr_links, name='docuseal_link_list'),
    path('docuseal/refresh/', docuseal.docuseal_refresh_page, name='docuseal_refresh'),
    path('docuseal/refresh/all/', docuseal.refresh_docuseal, name='refresh_docuseal'),
    path('docuseal/refresh/by-token/', docuseal.refresh_docuseal_by_token, name='refresh_docuseal_by_token'),
    path('docuseal/refresh/new/', docuseal.fetch_new_docuseal, name='fetch_new_docuseal'),
    path('docuseal/webhook/', docuseal.receive_webhook, name='receive_webhook'),
])

# Stripe
urlpatterns.extend([
    path('stripe/links/', stripe.payment_link_list, name='payment_link_list'),
    path('stripe/refresh/', stripe.stripe_refresh_page, name='stripe_refresh'),
    path('stripe/refresh/by-token/', stripe.refresh_stripe_by_token, name='refresh_stripe_by_token'),
    path('stripe/fetch-new/payment-links/', stripe.fetch_product_and_price, name='fetch_product_and_price'),
    path('stripe/fetch-new/subscriptions/', stripe.fetch_subscription_and_customer, name='fetch_subscription_and_customer'),
    path('stripe/refresh/payment-links/', stripe.refresh_product_and_price, name='refresh_product_and_price'),
    path('stripe/refresh/subscriptions/', stripe.refresh_subscription_and_customer, name='refresh_subscription_and_customer'),
    path('stripe/webhook/', stripe.receive_webhook, name='receive_webhook'),
])
