from django.contrib import admin
from django.urls import path

from subwaive import docuseal
from subwaive import stripe
from subwaive import person
from subwaive import event
from subwaive import link

# Admin
urlpatterns = [
    path('admin/', admin.site.urls),
]

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

# Person
urlpatterns.extend([
    path('email/<int:email_id>/unmerge/', person.unmerge_people, name='unmerge_people'),
    path('email/<int:email_id>/prefer/', person.set_preferred_email, name='set_preferred_email'),
    path('person/search/', person.person_search, name='person_search'),
    path('person/all/', person.person_list, name='person_list'),
    path('person/members/', person.member_list, name='member_list'),
    path('person/<int:person_id>/', person.person_card, name='person_card'),
    path('person/<int:person_id>/docuseal/', person.person_docuseal, name='person_docuseal'),
    path('person/<int:person_id>/edit/', person.person_edit, name='person_edit'),
    path('person/<int:person_id>/name/<int:important_field_id>/docuseal/', person.set_docuseal_name, name='set_docuseal_name'),
    path('person/<int:person_id>/name/<stripe_id>/stripe/', person.set_stripe_name, name='set_stripe_name'),
    path('person/<int:merge_child_id>/merge/', person.merge_people, name='merge_people'),
    path('person/<int:merge_child_id>/merge/<int:merge_parent_id>/', person.merge_people, name='merge_people'),
    path('person/<int:person_id>/stripe/', person.person_stripe, name='person_stripe'),
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
