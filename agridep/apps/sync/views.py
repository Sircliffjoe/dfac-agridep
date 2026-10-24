from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from .services import ingest_kobo_submission, process_sync_push, generate_sync_pull

class KoboWebhookView(APIView):
    """
    KoboToolbox & ODK Collect webhook endpoint.
    Accepts automated form submissions from rural field enumerators.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=dict,
        responses={200: OpenApiResponse(description="Submission ingested successfully")}
    )
    def post(self, request):
        payload = request.data
        if not payload:
            return Response({"error": "Empty payload received"}, status=status.HTTP_400_BAD_REQUEST)
        
        success, message = ingest_kobo_submission(payload, user=request.user if request.user.is_authenticated else None)
        status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        return Response({"status": "success" if success else "failed", "message": message}, status=status_code)

class SyncPushView(APIView):
    """
    Batch outbox push endpoint for Flutter Drift SQLite mobile app.
    Idempotent by client_id.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=dict,
        responses={200: OpenApiResponse(description="Batch sync processed")}
    )
    def post(self, request):
        operations = request.data.get('operations', [])
        result = process_sync_push(request.user, operations)
        return Response(result, status=status.HTTP_200_OK)

class SyncPullView(APIView):
    """
    Delta sync pull endpoint for Flutter Drift SQLite mobile app.
    Returns changed records scoped to the officer's assigned farmers since the given cursor.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description="Delta sync records returned")}
    )
    def get(self, request):
        since_cursor = request.query_params.get('since')
        result = generate_sync_pull(request.user, since_cursor)
        return Response(result, status=status.HTTP_200_OK)
