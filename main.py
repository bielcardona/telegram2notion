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
NOTION_PAGE_ID = os.environ["NOTION_PAGE_ID"]

notion = Client(auth=NOTION_TOKEN)
# Recuperam la pàgina una sola vegada
## page = notion.get_page(NOTION_PAGE_ID)

database = notion.databases.retrieve(NOTION_DATABASE_ID)
NOTION_DATA_SOURCE_ID = database['data_sources'][0]['id']

last_run = time.time()
last_page_id = None

DELTA_TIME = 10  # segons

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

def image_block(upload_id):
    return {
        "object": "block",
        "type": "image",
        "image": {
            "type": "file_upload",
            "file_upload": {
                "id": upload_id
            }
        }
    }

async def create_page_with_title(title: str):
    new_page = notion.pages.create(
        parent={"data_source_id": NOTION_DATA_SOURCE_ID},
        properties=page_block("Name", title),
    )
    return new_page

async def add_text_to_page(page_id: str, text: str):
    notion.blocks.children.append(block_id=page_id, children=[paragraph_block(text)])

async def add_image_to_page(page_id: str, image_file):
    upload = notion.file_uploads.create()
    upload_id = upload['id']
    notion.file_uploads.send(file_upload_id=upload_id, file=image_file)
    notion.blocks.children.append(block_id=page_id,children=[image_block(upload_id)])

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

    # --- Tipus de missatge ---
    if message.text:
        message_type = "text"

    elif message.photo:
        message_type = "photo"

    elif message.video:
        message_type = "video"

    elif message.voice:
        message_type = "voice"

    elif message.audio:
        message_type = "audio"

    elif message.document:
        message_type = "document"

    else:
        message_type = "unknown"

    if last_page_id is None or now - last_run >= DELTA_TIME:
        page = await create_page_with_title(message.text if message.text else "Nou missatge")
        last_page_id = page['id']

    # --- Processament segons tipus ---
    if message_type == "text":
        # TODO: processar text
        text = message.text
        await add_text_to_page(last_page_id, text)

    elif message_type == "photo":
        # Agafam la foto amb més resolució
        photo = message.photo[-1]

        # Recuperam el fitxer de Telegram
        telegram_file = await context.bot.get_file(photo.file_id)

        # Descarregam la imatge en memòria
        image_bytes = await telegram_file.download_as_bytearray()

        from io import BytesIO
        image_file = BytesIO(image_bytes)
        image_file.name = "photo.jpg"  # Notion necessita un nom de fitxer

        # Pujam la imatge a Notion
        await add_image_to_page(last_page_id, image_file)

    elif message_type == "video":
        # TODO: descarregar i pujar el vídeo a Notion
        pass

    elif message_type == "voice":
        # TODO: transcriure àudio (voice) i afegir-lo a Notion
        pass

    elif message_type == "audio":
        # TODO: tractar àudio llarg
        pass

    elif message_type == "document":
        # TODO: pujar document adjunt a Notion
        pass

    else:
        # TODO: gestionar missatges no suportats
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