# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-08-28 22:19
from __future__ import unicode_literals

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('contentcuration', '0115_index_contentnode_node_id_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentnode',
            name='complete',
            field=models.BooleanField(default=True),
        ),
    ]
