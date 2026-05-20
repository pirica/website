from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_add_password_setup_notified_at"),
    ]

    operations = [
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "django_openid_auth_useropenid" CASCADE;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "django_openid_auth_nonce" CASCADE;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "django_openid_auth_association" CASCADE;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
