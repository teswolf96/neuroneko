from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Old route, can be removed or commented out if ChatConsumer is no longer used
    # re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()), 
    re_path(r'ws/chat/(?P<chat_id>\d+)/$', consumers.StreamingChatConsumer.as_asgi()), # Changed regex to \d+ for integer IDs
]
