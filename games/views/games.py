"""API views module"""

# lint: disable=too-few-public-methods
from __future__ import absolute_import
from django.db.models import Q
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework import filters, generics, permissions
from rest_framework.response import Response

from games import models, serializers
from providers.models import Provider
from accounts.models import User


class GameListView(generics.GenericAPIView):
    """Return a list of games"""

    filter_backends = (filters.SearchFilter,)
    search_fields = ("slug", "name")

    def get_queryset(self):
        """Return the query set for the game list

        This view can be queried by the client to get all lutris games
        available based on a series of criteria such as a list of slugs or GOG
        ids.
        """

        # Easter egg: Return a random game
        if "random" in self.request.GET:
            return [models.Game.objects.get_random(self.request.GET["random"])]

        if "with-installers" in self.request.GET:
            base_query = models.Game.objects.with_installer()
        else:
            base_query = models.Game.objects.published()

        # A list of slugs is sent from the client, we match them against Lutris
        # games.
        if "games" in self.request.GET:
            game_slugs = self.request.GET.getlist("games")
        elif "games" in self.request.data:
            game_slugs = self.request.data.get("games")
        else:
            game_slugs = None
        if game_slugs:
            return base_query.filter(
                Q(slug__in=game_slugs) | Q(aliases__slug__in=game_slugs),
            )
        # This is to be deprecated, starting from 0.5.8, the client won't use that anymore
        if "gogid" in self.request.data:
            gogids = [
                gogid for gogid in self.request.data["gogid"] if gogid.isnumeric()
            ]
            return base_query.filter(
                provider_games__slug__in=gogids, provider_games__provider__name="gog"
            )
        if "humblestoreid" in self.request.data:
            return base_query.filter(
                provider_games__slug__in=self.request.data["humblestoreid"],
                provider_games__provider__name="humblebundle",
            )
        if (
            not self.request.user.is_authenticated
            or not self.request.user.show_adult_content
        ):
            base_query = base_query.exclude(Q(flags=models.Game.flags.adult_only))
        return base_query

    def get_serializer_class(self):
        """Return the appropriate serializer

        Adding ?installer=1 to the url adds the installers to the games
        """
        if self.request.GET.get("installers") == "1":
            return serializers.GameInstallersSerializer
        return serializers.GameSerializer

    def get(self, _request):
        """GET request"""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        """POST request"""
        # Using POST instead of GET is a violation of API rules but it's the
        # only way to send a huge payload to the server. GET querystrings only
        # support a limited number of characters (depending on the web server or
        # the browser used) whereas POST request do not have this limitation.
        return self.get(request)


class ServiceGameListView(generics.GenericAPIView):
    """API view to match service games with Lutris games"""

    serializer_class = serializers.GameSerializer

    def get_queryset(self, service):  # pylint: disable=arguments-differ
        """Match lutris games against service appids"""
        appids = self.request.data.get("appids")
        if not appids:
            return models.Game.objects.none()
        return models.Game.objects.filter(
            change_for__isnull=True,
            provider_games__slug__in=appids,
            provider_games__provider__name=service,
        )

    def post(self, _request, service):
        """This view is post only and accepts a payload in JSON"""
        try:
            Provider.objects.get(name=service)
        except Provider.DoesNotExist:
            return Response("Bwahahah, screw you.", status=status.HTTP_400_BAD_REQUEST)

        queryset = self.filter_queryset(self.get_queryset(service))
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class GameLibraryView(generics.RetrieveAPIView):
    """Legacy route for the library"""

    serializer_class = serializers.GameLibrarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, username):  # pylint: disable=arguments-differ
        username = request.user.username
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                return Response(status=404)
            except User.MultipleObjectsReturned:
                return Response(status=404)
        if user != request.user and not user.is_staff:
            return Response(status=404)
        library = models.GameLibrary.objects.prefetch_related(
            "games", "games__game"
        ).get(user=user)
        serializer = serializers.GameLibrarySerializer(library)
        return Response(serializer.data)


class GameDetailView(generics.RetrieveAPIView):
    """Return the details of a game referenced by its slug"""

    serializer_class = serializers.GameDetailSerializer
    lookup_field = "slug"
    queryset = models.Game.objects.filter(change_for__isnull=True)


class GameInstallersView(generics.RetrieveAPIView):
    """Return game details along with installers"""

    serializer_class = serializers.GameInstallersSerializer
    lookup_field = "slug"
    queryset = models.Game.objects.filter(change_for__isnull=True)


class GameStatsView(APIView):
    """View for game statistics"""

    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def get(_request, _format=None):
        """Return game statistics"""
        statistics = {}

        statistics["games"] = models.Game.objects.all().count()
        statistics["published_games"] = models.Game.objects.filter(
            is_public=True
        ).count()
        statistics["unpublished_games"] = models.Game.objects.filter(
            is_public=False
        ).count()
        statistics["game_changes"] = models.Game.objects.filter(
            change_for__isnull=False
        ).count()

        statistics["game_submissions"] = models.GameSubmission.objects.all().count()
        statistics["accepted_game_submissions"] = models.GameSubmission.objects.filter(
            accepted_at__isnull=False
        ).count()
        statistics["pending_game_submissions"] = models.GameSubmission.objects.filter(
            accepted_at__isnull=True,
            game__change_for__isnull=True,
        ).count()
        statistics["pending_game_changes"] = models.GameSubmission.objects.filter(
            accepted_at__isnull=True,
            game__change_for__isnull=False,
        ).count()
        statistics["installers"] = models.Installer.objects.all().count()
        statistics["published_installers"] = models.Installer.objects.get_filtered(
            {"published": True}
        ).count()
        statistics["submitted_drafts"] = models.InstallerDraft.objects.filter(
            draft=False
        ).count()
        statistics["drafts"] = models.InstallerDraft.objects.all().count()
        statistics["screenshots"] = models.Screenshot.objects.all().count()
        statistics["published_screenshots"] = models.Screenshot.objects.filter(
            published=True
        ).count()
        statistics["unpublished_screenshots"] = models.Screenshot.objects.filter(
            published=False
        ).count()

        return Response(statistics)


class GameMergeView(APIView):
    """View used to merge 2 games together"""

    @staticmethod
    def post(request, slug, other_slug):
        """Merge a game with another one.
        This view is restricted to staff members
        """
        if not request.user.is_staff:
            raise PermissionDenied
        original_game = get_object_or_404(models.Game, slug=slug)
        other_game = get_object_or_404(models.Game, slug=other_slug)
        original_game.merge_with_game(other_game)
        return Response({"result": "ok"})


class GameSubmissionsView(generics.ListAPIView):
    """List all game submissions"""

    serializer_class = serializers.GameSubmissionSerializer
    permission_classes = (permissions.IsAdminUser,)
    get_new_submissions = True

    def get_queryset(self):
        return (
            models.GameSubmission.objects.filter(
                accepted_at__isnull=True,
                game__change_for__isnull=self.get_new_submissions,
            )
            .prefetch_related("game", "user", "game__provider_games")
            .order_by("-created_at")
        )


class GameChangesView(GameSubmissionsView):
    """List all game changes"""

    get_new_submissions = False


class GameSubmissionAcceptView(APIView):
    """Accept a user submission"""

    @staticmethod
    def post(request, submission_id):
        """Process the submission"""
        if not request.user.is_staff:
            raise PermissionDenied
        game_submission = get_object_or_404(models.GameSubmission, pk=submission_id)
        if request.data["accepted"]:
            game_submission.accept()
            accepted = True
        else:
            game_submission.delete()
            accepted = False
        return Response({"id": game_submission.id, "accepted": accepted})


class ScreenshotView(generics.ListAPIView):
    """List all game submissions"""

    serializer_class = serializers.ScreenshotSerializer
    permission_classes = (permissions.IsAdminUser,)

    def get_queryset(self):
        return models.Screenshot.objects.unpublished()


class ScreenshotReviewView(APIView):
    """Accept of refuse a screenshot"""

    @staticmethod
    def post(request, screenshot_id):
        if not request.user.is_staff:
            raise PermissionDenied

        screenshot = get_object_or_404(models.Screenshot, pk=screenshot_id)
        if request.data["accepted"] == "accept":
            screenshot.published = True
            screenshot.save()
            accepted = True
        elif request.data["accepted"] == "refuse":
            screenshot.image.delete()
            screenshot.delete()
            accepted = False
        return Response({"id": screenshot.id, "accepted": accepted})
