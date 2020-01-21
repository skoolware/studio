# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2018-03-29 17:51
from __future__ import unicode_literals

import jsonfield.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contentcuration', '0083_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='channel',
            name='content_defaults',
            field=jsonfield.fields.JSONField(default={b'author': None, 'auto_derive_audio_thumbnail': True, 'auto_derive_document_thumbnail': True, 'auto_derive_exercise_thumbnail': True, 'auto_derive_html5_thumbnail': True,
                                                      'auto_derive_video_thumbnail': True, 'auto_randomize_questions': True, 'copyright_holder': None, 'language': None, 'license': None, 'license_description': None, 'm_value': 5, 'mastery_model': 'num_correct_in_a_row_5', 'n_value': 5}),
        ),
        migrations.AddField(
            model_name='user',
            name='content_defaults',
            field=jsonfield.fields.JSONField(default={b'author': None, 'auto_derive_audio_thumbnail': True, 'auto_derive_document_thumbnail': True, 'auto_derive_exercise_thumbnail': True, 'auto_derive_html5_thumbnail': True,
                                                      'auto_derive_video_thumbnail': True, 'auto_randomize_questions': True, 'copyright_holder': None, 'language': None, 'license': None, 'license_description': None, 'm_value': 5, 'mastery_model': 'num_correct_in_a_row_5', 'n_value': 5}),
        ),
    ]
