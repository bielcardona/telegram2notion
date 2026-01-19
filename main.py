import os

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

from notion_client import Client

import time

# --- Config ---

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
MAIN_FIELD_NAME = os.environ.get("MAIN_FIELD_NAME", "Name")

notion = Client(auth=NOTION_TOKEN)

database = notion.databases.retrieve(NOTION_DATABASE_ID)
NOTION_DATA_SOURCE_ID = database['data_sources'][0]['id']

last_run = time.time()
last_page_id = None

DELTA_TIME = 10  # segons

from openai import AsyncOpenAI

openai_client = AsyncOpenAI()

async def transcribe_audio(audio_file):
    audio_file.seek(0)
    transcript = await openai_client.audio.transcriptions.create(
        model="gpt-4o-transcribe",
        file=audio_file,
        response_format="text",
        language="ca"  # o "es" / "en"
    )
    return transcript

def page_block(title_field, title):
    return {
        title_field: {
            "title": [
                {
                    "text": {
                        "content": title
                    }
                }
            ]
        },
    }

def paragraph_block(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }

def file_block(kind,upload_id):
    if kind not in ['file', 'image', 'pdf', 'audio', 'video']:
        return paragraph_block('file kind not supported')

    return {
        "object": "block",
        "type": kind,
        kind: {
            "type": "file_upload",
            "file_upload": {
                "id": upload_id
            }
        }
    }

def image_block(upload_id):
    return file_block("image",upload_id)

async def create_page_with_title(title: str):
    new_page = notion.pages.create(
        parent={"data_source_id": NOTION_DATA_SOURCE_ID},
        properties=page_block(MAIN_FIELD_NAME, title),
    )
    return new_page

async def add_text_to_page(page_id: str, text: str):
    notion.blocks.children.append(block_id=page_id, children=[paragraph_block(text)])

async def add_image_to_page(page_id: str, image_file):
    upload = notion.file_uploads.create()
    upload_id = upload['id']
    notion.file_uploads.send(file_upload_id=upload_id, file=image_file)
    notion.blocks.children.append(block_id=page_id,children=[image_block(upload_id)])

# --- Message Type Handlers ---
async def handle_text_message(message, page_id):
    text = message.text
    await add_text_to_page(page_id, text)


async def handle_photo_message(message, context, page_id):
    photo = message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    image_bytes = await telegram_file.download_as_bytearray()

    from io import BytesIO
    image_file = BytesIO(image_bytes)
    image_file.name = "photo.jpg"

    await add_image_to_page(page_id, image_file)


async def handle_voice_message(message, context, page_id):
    transcription = await get_text_from_voice_message(message, context)
    await add_text_to_page(
        page_id,
        f"🎤: {transcription}"
    )

async def get_text_from_voice_message(message, context):
    voice = message.voice
    telegram_file = await context.bot.get_file(voice.file_id)
    audio_bytes = await telegram_file.download_as_bytearray()
    from io import BytesIO
    audio_file = BytesIO(audio_bytes)
    audio_file.name="voice.ogg"
    try:
        transcription = await transcribe_audio(audio_file)
    except Exception as e:
        transcription = f"[Error transcrivint àudio: {e}]"
    return transcription


async def handle_video_message(message, context, page_id):
    pass  # TODO


async def handle_audio_message(message, context, page_id):
    pass  # TODO


async def handle_document_message(message, context, page_id):
    document = message.document
    # Només tractam PDFs
    if document.mime_type != "application/pdf":
        await add_text_to_page(
            page_id,
            f"📎 Document no suportat: {document.file_name} ({document.mime_type})"
        )
        return
    # Obtenir el fitxer de Telegram
    telegram_file = await context.bot.get_file(document.file_id)
    # Descarregar en memòria
    file_bytes = await telegram_file.download_as_bytearray()
    from io import BytesIO
    pdf_file = BytesIO(file_bytes)
    pdf_file.name = document.file_name or "document.pdf"
    # Afegir el bloc PDF a la pàgina
    upload = notion.file_uploads.create()
    upload_id = upload['id']
    notion.file_uploads.send(file_upload_id=upload_id, file=pdf_file)
    notion.blocks.children.append(
        block_id=page_id,
        children=[file_block("pdf", upload_id)]
    )


# --- Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(update)

    if not update.message:
        return

    user = update.message.from_user.first_name

    global last_page_id
    global last_run

    now = time.time()

    message = update.message

    new_page = False
    if last_page_id is None or now - last_run >= DELTA_TIME:
        new_page = True
        if message.text:
            title = message.text
        elif message.voice:
            title = await get_text_from_voice_message(message, context)
        else:
            title = "Nou missatge"
        page = await create_page_with_title(title)
        last_page_id = page['id']

    # --- Tipus de missatge ---
    if message.text:
        if not new_page:
            await handle_text_message(message, last_page_id)
        message_type = "text"

    elif message.photo:
        await handle_photo_message(message, context, last_page_id)
        message_type = "photo"

    elif message.voice:
        if not new_page:
            await handle_voice_message(message, context, last_page_id)
            message_type = "voice"

    elif message.video:
        await handle_video_message(message, context, last_page_id)
        message_type = "video"

    elif message.audio:
        await handle_audio_message(message, context, last_page_id)
        message_type = "audio"

    elif message.document:
        await handle_document_message(message, context, last_page_id)
        message_type = "document"

    else:
        message_type = "unknown"
        print("Tipus de missatge no suportat")

    print(f"[Notion] {user}: {message_type}")
    last_run = time.time()

# --- Main ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.ALL, handle_message)
    )

    print("🤖 Bot escoltant...")
    app.run_polling()

if __name__ == "__main__":
    main()