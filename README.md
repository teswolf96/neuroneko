# AI Chat Interface

This project is a Django-based web application that provides a user interface for interacting with various AI models. It allows users to manage AI API configurations, engage in threaded chat conversations, organize these chats, and customize their settings.

## Features

*   **User Authentication:** Secure user signup, login, and logout functionality.
*   **AI Configuration Management:**
    *   Define multiple **AI Endpoints** (e.g., different API providers or self-hosted models) with custom names, URLs, and API keys.
    *   Configure specific **AI Models** for each endpoint (e.g., "gpt-4-turbo", "claude-3-opus") with their respective model IDs and default generation parameters like temperature and max tokens.
    *   Test API endpoint configurations directly from the UI.
*   **Advanced Chat Interface:**
    *   Engage in **threaded conversations**, allowing for complex dialogue structures and branching.
    *   Create new chats, optionally using a default AI model from user settings.
    *   Chat titles can be manually set or **automatically regenerated** using an AI model based on the conversation's context.
    *   Select a specific AI model for each chat session.
*   **Chat Organization:**
    *   Organize chats into **Folders** for better management.
    *   Create, rename, and delete folders.
    *   Move chats between folders.
*   **Message Management:**
    *   Add, edit, and delete messages within a chat.
    *   Navigate different branches of a conversation using the "active child" feature.
*   **User Customization:**
    *   Personalize the experience via **User Settings**, including:
        *   Setting a default AI model.
        *   Defining a default system prompt for AI interactions.
        *   Setting a default temperature for AI responses.
    *   The system remembers the last active chat for a seamless experience.
*   **Real-time Capabilities:** Utilizes Django Channels for potential real-time communication features (e.g., live chat updates).
*   **Automatic Setup for New Users:** New users get a pre-configured default AI endpoint, AI model, user settings, a sample chat, and a welcome message to get started quickly.

## Technology Stack

*   **Backend:**
    *   Python 3.x
    *   Django 4.2+
    *   Django Channels (for WebSocket/real-time features)
    *   Daphne (ASGI server)
*   **Database:** SQLite (default, configurable in Django settings)
*   **HTTP Client:** `httpx`
*   **AI Integration:** `anthropic` SDK (for Anthropic models, adaptable for others)
*   **Frontend:** HTML, CSS, JavaScript (rendered via Django Templates)

## Prerequisites

*   Python 3.8 or higher
*   pip (Python package installer)
*   Git (for cloning the repository)

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <project-directory>
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Apply database migrations:**
    ```bash
    python manage.py migrate
    ```

5.  **Create a superuser (for admin access):**
    ```bash
    python manage.py createsuperuser
    ```
    Follow the prompts to set a username, email, and password.

6.  **Run the development server:**
    ```bash
    daphne -p 8000 chat_project.asgi:application
    ```
    The application will typically be available at `http://127.0.0.1:8000/`.

## Usage Guide

1.  **Sign Up / Login:**
    *   Navigate to the application in your browser.
    *   You have to manually create accounts using the admin page once logged in as a superuser.

2.  **Configure AI Endpoints and Models:**
    *   Go to the API Configuration section.
    *   Add a new AI Endpoint by providing a name, the base URL of the AI provider's API, and your API key.
    *   Once an endpoint is created, add AI Models associated with that endpoint. Specify a custom name for the model (e.g., "My GPT-4") and the actual model ID used by the API (e.g., "gpt-4-turbo").

3.  **Start and Manage Chats:**
    *   From the main interface, create a new chat.
    *   The chat will use your default AI model unless you change it in the chat settings.
    *   Type messages and interact with the AI.
    *   Use the interface options to rename the chat, delete it, or move it to a folder.

4.  **Using Folders:**
    *   Create folders to organize your chats.
    *   Drag and drop chats into folders or use an option to move them.

5.  **User Settings:**
    *   Access your user settings to customize your default AI model, default system prompt, and other preferences.

## Project Structure

*   `chat_project/`: Contains the main Django project configuration (`settings.py`, `urls.py`).
*   `chat/`: The core Django app containing models, views, forms, templates, and logic for the chat functionality.
    *   `models.py`: Defines the database schema (Users, AI Endpoints, AI Models, Chats, Messages, Folders).
    *   `views.py`: Handles request-response logic and serves HTML pages.
    *   `consumers.py`: (Assumed for Django Channels) Handles WebSocket connections for real-time features.
    *   `api_client.py`: Contains logic for interacting with external AI APIs.
    *   `templates/`: HTML templates for the user interface.
*   `manage.py`: Django's command-line utility.
*   `requirements.txt`: Lists project dependencies.
*   `README.md`: This file.

## Contributing

Details on contributing to the project will be added later.

## License

This project is currently unlicensed. (Or specify a license if one is chosen)
