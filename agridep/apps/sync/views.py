from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from .services import (
    ingest_kobo_submission,
    process_sync_push,
    generate_sync_pull,
    handle_resumable_media_chunk,
)

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


class MediaUploadView(APIView):
    """
    Resumable chunked media upload endpoint for Flutter mobile background sync queue.
    Accepts multipart/form-data with client_id, file, total_size, and offset.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=dict,
        responses={200: OpenApiResponse(description="Media chunk uploaded successfully")}
    )
    def post(self, request):
        client_id = request.data.get('client_id')
        file_obj = request.FILES.get('file')
        file_name = request.data.get('file_name', file_obj.name if file_obj else 'photo.jpg')
        total_size = int(request.data.get('total_size', file_obj.size if file_obj else 0))
        offset = int(request.data.get('offset', 0))
        file_category = request.data.get('file_category', 'INSPECTION_PHOTO')

        if not client_id or not file_obj:
            return Response({"error": "client_id and file are required."}, status=status.HTTP_400_BAD_REQUEST)

        result = handle_resumable_media_chunk(
            user=request.user,
            client_id=client_id,
            file_name=file_name,
            chunk_file=file_obj,
            total_size=total_size,
            offset=offset,
            file_category=file_category
        )
        return Response(result, status=status.HTTP_200_OK)

