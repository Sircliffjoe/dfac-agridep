from datetime import datetime
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status

from agridep.apps.reporting.services import (
    compute_donor_me_indicators,
    generate_donor_excel_report,
    generate_donor_pdf_report,
)


class DonorIndicatorsAPIView(APIView):
    """
    Returns aggregated PIND / GIZ M&E indicators in structured JSON format.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        donor = request.query_params.get('donor', 'PIND')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_date = None
        end_date = None
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        data = compute_donor_me_indicators(start_date=start_date, end_date=end_date, donor=donor)
        return Response(data, status=status.HTTP_200_OK)


class DonorExcelExportAPIView(APIView):
    """
    Generates and downloads an official multi-tab Excel (.xlsx) M&E report.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        donor = request.query_params.get('donor', 'PIND')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_date = None
        end_date = None
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        data = compute_donor_me_indicators(start_date=start_date, end_date=end_date, donor=donor)
        excel_buffer = generate_donor_excel_report(data)

        filename = f"DFAC_AgriDEP_{donor.upper()}_ME_Report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class DonorPDFExportAPIView(APIView):
    """
    Generates and downloads an official publication-grade PDF M&E report.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        donor = request.query_params.get('donor', 'PIND')
        start_str = request.query_params.get('start_date')
        end_str = request.query_params.get('end_date')

        start_date = None
        end_date = None
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        data = compute_donor_me_indicators(start_date=start_date, end_date=end_date, donor=donor)
        pdf_buffer = generate_donor_pdf_report(data)

        filename = f"DFAC_AgriDEP_{donor.upper()}_ME_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type="application/pdf"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
