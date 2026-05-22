from django.db import migrations, models
from django.db.models import Count


def dedupe_gamealias_slugs(apps, schema_editor):
    GameAlias = apps.get_model("games", "GameAlias")
    Game = apps.get_model("games", "Game")

    duplicate_slugs = list(
        GameAlias.objects.values("slug")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("slug", flat=True)
    )
    for slug in duplicate_slugs:
        aliases = list(GameAlias.objects.filter(slug=slug).order_by("pk"))
        keeper, losers = aliases[0], aliases[1:]
        loser_summary = [(a.pk, a.game_id) for a in losers]
        print(
            f"GameAlias dedupe: slug={slug!r} keep pk={keeper.pk} "
            f"(game_id={keeper.game_id}); delete (pk, game_id)={loser_summary}"
        )
        GameAlias.objects.filter(pk__in=[a.pk for a in losers]).delete()

    game_slugs = set(Game.objects.exclude(slug__isnull=True).values_list("slug", flat=True))
    shadowing = GameAlias.objects.filter(slug__in=game_slugs)
    for alias in shadowing:
        print(
            f"GameAlias dedupe: delete alias pk={alias.pk} slug={alias.slug!r} "
            f"on game_id={alias.game_id} (shadows existing Game.slug)"
        )
    shadowing.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0085_alter_regression_bug_url"),
    ]

    operations = [
        migrations.RunPython(dedupe_gamealias_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="gamealias",
            name="slug",
            field=models.SlugField(max_length=255, unique=True),
        ),
    ]
