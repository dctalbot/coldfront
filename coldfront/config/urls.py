"""
Coldfront URL Configuration
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

import coldfront.core.portal.views as portal_views

admin.site.site_header = 'ColdFront Administration'
admin.site.site_title = 'ColdFront Administration'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name="robots"),
    path('', portal_views.home, name='home'),
    path('center-summary', portal_views.center_summary, name='center-summary'),
    path('subscription-summary', portal_views.subscription_summary, name='subscription-summary'),
    path('subscription-by-fos', portal_views.subscription_by_fos, name='subscription-by-fos'),
    path('user/', include('coldfront.core.user.urls')),
    path('project/', include('coldfront.core.project.urls')),
    path('subscription/', include('coldfront.core.subscription.urls')),
    path('grant/', include('coldfront.core.grant.urls')),
    path('publication/', include('coldfront.core.publication.urls')),
]


if 'coldfront.plugins.iquota' in settings.EXTRA_APPS:
    urlpatterns.append(path('iquota/', include('coldfront.plugins.iquota.urls')))

if 'coldfront.plugins.mokey_oidc' in settings.EXTRA_APPS:
    urlpatterns.append(path('oidc/', include('mozilla_django_oidc.urls')))

if 'django_su.backends.SuBackend' in settings.EXTRA_AUTHENTICATION_BACKENDS:
    urlpatterns.append(path('su/', include('django_su.urls')))
