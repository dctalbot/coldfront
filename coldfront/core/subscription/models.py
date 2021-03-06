import datetime
import importlib
import logging
from ast import literal_eval

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import mark_safe
from django.utils.module_loading import import_string

from coldfront.core.project.models import Project
from coldfront.core.resource.models import Resource
from coldfront.core.utils.common import import_from_settings
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

logger = logging.getLogger(__name__)


SUBSCRIPTION_FUNCS_ON_EXPIRE = import_from_settings(
    'SUBSCRIPTION_FUNCS_ON_EXPIRE', [])
SLURM_ACCOUNT_ATTRIBUTE_NAME = import_from_settings(
    'SLURM_ACCOUNT_ATTRIBUTE_NAME', 'slurm_account_name')


class SubscriptionStatusChoice(TimeStampedModel):
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name', ]


class Subscription(TimeStampedModel):
    """ Subscription to a system Resource. """
    project = models.ForeignKey(Project, on_delete=models.CASCADE,)
    resources = models.ManyToManyField(Resource)
    status = models.ForeignKey(
        SubscriptionStatusChoice, on_delete=models.CASCADE, verbose_name='Status')
    quantity = models.IntegerField(default=1)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    justification = models.TextField()
    description = models.CharField(max_length=512, blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['end_date', ]

        permissions = (
            ('can_view_all_subscriptions', 'Can view all subscriptions'),
            ('can_review_subscription_requests',
             'Can review subscription requests'),
            ('can_manage_invoice', 'Can manage invoice'),
        )

    def clean(self):
        if self.status.name == 'Expired':
            if not self.end_date:
                raise ValidationError('You have to set the end date.')

            if self.end_date > datetime.datetime.now().date():
                raise ValidationError(
                    'End date cannot be greater than today.')

            if self.start_date > self.end_date:
                raise ValidationError(
                    'End date cannot be greater than start date.')

        elif self.status.name == 'Active':
            if not self.start_date:
                raise ValidationError('You have to set the start date.')

            if not self.end_date:
                raise ValidationError('You have to set the end date.')

            if self.start_date > self.end_date:
                raise ValidationError(
                    'Start date cannot be greater than the end date.')

    def save(self, *args, **kwargs):
        if self.pk:
            old_obj = Subscription.objects.get(pk=self.pk)
            if old_obj.status.name != self.status.name and self.status.name == 'Expired':
                for func_string in SUBSCRIPTION_FUNCS_ON_EXPIRE:
                    func_to_run = import_string(func_string)
                    func_to_run(self.pk)

        super().save(*args, **kwargs)

    @property
    def expires_in(self):
        return (self.end_date - datetime.date.today()).days

    @property
    def get_information(self):
        html_string = ''
        for attribute in self.subscriptionattribute_set.all():

            if attribute.subscription_attribute_type.name in [SLURM_ACCOUNT_ATTRIBUTE_NAME, ]:
                html_string += '%s: %s <br>' % (
                    attribute.subscription_attribute_type.name, attribute.value)

            if hasattr(attribute, 'subscriptionattributeusage'):
                try:
                    percent = round(float(attribute.subscriptionattributeusage.value) /
                                    float(attribute.value) * 10000) / 100
                except ValueError:
                    percent = 'Invalid Value'
                    logger.error("Subscription attribute '%s' is not an int but has a usage",
                                 attribute.subscription_attribute_type.name)

                string = '{}: {}/{} ({} %) <br>'.format(
                    attribute.subscription_attribute_type.name,
                    attribute.subscriptionattributeusage.value,
                    attribute.value,
                    percent
                )
                html_string += string

        return mark_safe(html_string)

    @property
    def get_resources_as_string(self):
        return ', '.join([ele.name for ele in self.resources.all().order_by('-is_subscribable')])

    @property
    def get_parent_resource(self):
        return self.resources.filter(is_subscribable=True).first()

    def get_attribute(self, name):
        attr = self.subscriptionattribute_set.filter(
            subscription_attribute_type__name=name).first()
        if attr:
            return attr.value
        return None

    def set_usage(self, name, value):
        attr = self.subscriptionattribute_set.filter(
            subscription_attribute_type__name=name).first()
        if not attr:
            return

        if not attr.subscription_attribute_type.has_usage:
            return

        if not SubscriptionAttributeUsage.objects.filter(subscription_attribute=attr).exists():
            usage = SubscriptionAttributeUsage.objects.create(
                subscription_attribute=attr)
        else:
            usage = attr.subscriptionattributeusage

        usage.value = value
        usage.save()

    def get_attribute_list(self, name):
        attr = self.subscriptionattribute_set.filter(
            subscription_attribute_type__name=name).all()
        return [a.value for a in attr]

    def __str__(self):
        return "%s (%s)" % (self.get_parent_resource.name, self.project.pi)


class SubscriptionAdminNote(TimeStampedModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    note = models.TextField()

    def __str__(self):
        return self.note


class SubscriptionUserNote(TimeStampedModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    is_private = models.BooleanField(default=True)
    note = models.TextField()

    def __str__(self):
        return self.note


class AttributeType(TimeStampedModel):
    """ AttributeType. """
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name', ]


class SubscriptionAttributeType(TimeStampedModel):
    """ SubscriptionAttributeType. """
    attribute_type = models.ForeignKey(AttributeType, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    has_usage = models.BooleanField(default=False)
    is_required = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    is_private = models.BooleanField(default=True)
    history = HistoricalRecords()

    def __str__(self):
        return '%s (%s)' % (self.name, self.attribute_type.name)

    class Meta:
        ordering = ['name', ]


class SubscriptionAttribute(TimeStampedModel):
    """ SubscriptionAttribute. """
    subscription_attribute_type = models.ForeignKey(
        SubscriptionAttributeType, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    value = models.CharField(max_length=128)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.subscription_attribute_type.has_usage and not SubscriptionAttributeUsage.objects.filter(subscription_attribute=self).exists():
            SubscriptionAttributeUsage.objects.create(
                subscription_attribute=self)

    def clean(self):
        if self.subscription_attribute_type.is_unique and self.subscription.subscriptionattribute_set.filter(subscription_attribute_type=self.subscription_attribute_type).exists():
            raise ValidationError("'{}' attribute already exists for this subscription.".format(
                self.subscription_attribute_type))

        expected_value_type = self.subscription_attribute_type.attribute_type.name.strip()

        if expected_value_type == "Int" and not isinstance(literal_eval(self.value), int):
            raise ValidationError(
                'Invalid Value "%s". Value must be an integer.' % (self.value))
        elif expected_value_type == "Float" and not (isinstance(literal_eval(self.value), float) or isinstance(literal_eval(self.value), int)):
            raise ValidationError(
                'Invalid Value "%s". Value must be a float.' % (self.value))
        elif expected_value_type == "Yes/No" and self.value not in ["Yes", "No"]:
            raise ValidationError(
                'Invalid Value "%s". Allowed inputs are "Yes" or "No".' % (self.value))
        elif expected_value_type == "Date":
            try:
                datetime.datetime.strptime(self.value.strip(), "%Y-%m-%d")
            except ValueError:
                raise ValidationError(
                    'Invalid Value "%s". Date must be in format YYYY-MM-DD' % (self.value))

    def __str__(self):
        return '%s' % (self.subscription_attribute_type.name)


class SubscriptionAttributeUsage(TimeStampedModel):
    """ SubscriptionAttributeUsage. """
    subscription_attribute = models.OneToOneField(
        SubscriptionAttribute, on_delete=models.CASCADE, primary_key=True)
    value = models.FloatField(default=0)
    history = HistoricalRecords()

    def __str__(self):
        return '{}: {}'.format(self.subscription_attribute.subscription_attribute_type.name, self.value)


class SubscriptionUserStatusChoice(TimeStampedModel):
    name = models.CharField(max_length=64)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name', ]


class SubscriptionUser(TimeStampedModel):
    """ SubscriptionUser. """
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.ForeignKey(SubscriptionUserStatusChoice, on_delete=models.CASCADE,
                               verbose_name='Subscription User Status')
    history = HistoricalRecords()

    def __str__(self):
        return '%s (%s)' % (self.user, self.subscription.resources.first().name)

    class Meta:
        verbose_name_plural = 'Subscription User Status'
        unique_together = ('user', 'subscription')


class SubscriptionAccount(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=64, unique=True)


    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name', ]
