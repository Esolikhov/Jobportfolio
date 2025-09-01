
from django.contrib import admin
from django.urls import path
from ocr_form.views import upload_image

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', upload_image, name='upload_image')
]
