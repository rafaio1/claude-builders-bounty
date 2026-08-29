# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    PLATFORM = os.getenv('PLATFORM', 'discord').lower()
    FAQ_FILE = os.getenv('FAQ_FILE', 'faq.json')
    LEAD_WEBHOOK_URL = os.getenv('LEAD_WEBHOOK_URL')
# adapters/base_adapter.py
from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    @abstractmethod
    async def send_message(self, channel_id: str, message: str):
        pass
    
    @abstractmethod
    async def get_user_info(self, user_id: str) -> dict:
        pass
    
    @abstractmethod
    def parse_message(self, raw_message: dict) -> dict:
        pass
# adapters/discord_adapter.py
import discord
from .base_adapter import BaseAdapter

class DiscordAdapter(BaseAdapter):
    def __init__(self, token: str):
        self.client = discord.Client(intents=discord.Intents.default())
        self.token = token
    
    async def start(self):
        await self.client.start(self.token)
    
    async def send_message(self, channel_id: int, message: str):
        channel = self.client.get_channel(channel_id)
        if channel:
            await channel.send(message)
    
    async def get_user_info(self, user_id: int) -> dict:
        user = self.client.get_user(user_id)
        if user:
            return {
                'id': user.id,
                'name': user.name,
                'discriminator': user.discriminator
            }
        return {}
    
    def parse_message(self, message: discord.Message) -> dict:
        return {
            'content': message.content,
            'user_id': message.author.id,
            'channel_id': message.channel.id,
            'username': message.author.name
        }
# adapters/telegram_adapter.py
from telegram import Update
from telegram.ext import Application
from .base_adapter import BaseAdapter

class TelegramAdapter(BaseAdapter):
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.token = token
    
    async def start(self):
        await self.application.initialize()
        await self.application.start()
    
    async def send_message(self, chat_id: int, message: str):
        await self.application.bot.send_message(chat_id=chat_id, text=message)
    
    async def get_user_info(self, user_id: int) -> dict:
        user = await self.application.bot.get_chat(user_id)
        return {
            'id': user.id,
            'name': user.first_name,
            'username': user.username or ''
        }
    
    def parse_message(self, update: Update) -> dict:
        message = update.message
        return {
            'content': message.text,
            'user_id': message.from_user.id,
            'channel_id': message.chat_id,
            'username': message.from_user.username or message.from_user.first_name
        }
# faq_responder.py
import json
import re

class FAQResponder:
    def __init__(self, faq_file: str = 'faq.json'):
        self.faq_file = faq_file
        self.faqs = self._load_faqs()
    
    def _load_faqs(self) -> dict:
        try:
            with open(self.faq_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def find_answer(self, question: str) -> str:
        question_lower = question.lower()
        
        for key, answer in self.faqs.items():
            if key.lower() in question_lower:
                return answer
        
        keywords = {
            'hello': 'greetings',
            'hi': 'greetings',
            'hey': 'greetings',
            'price': 'pricing',
            'cost': 'pricing',
            'help': 'support',
            'support': 'support',
            'hours': 'hours',
            'time': 'hours'
        }
        
        for keyword, faq_key in keywords.items():
            if keyword in question_lower:
                if isinstance(self.faqs.get(faq_key), list):
                    import random
                    return random.choice(self.faqs[faq_key])
                return self.faqs.get(faq_key, "I don't have an answer for that.")
        
        return "I don't have an answer for that. Please contact support for more information."
# lead_capture.py
import requests
from datetime import datetime

class LeadCaptureHandler:
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url
        self.leads = []
    
    def capture_lead(self, user_info: dict, message: str = "") -> bool:
        lead_data = {
            'user_id': user_info.get('user_id'),
            'username': user_info.get('username'),
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'source': 'bot'
        }
        
        self.leads.append(lead_data)
        
        if self.webhook_url:
            return self._send_to_webhook(lead_data)
        
        return True
    
    def _send_to_webhook(self, data: dict) -> bool:
        try:
            response = requests.post(self.webhook_url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send lead to webhook: {e}")
            return False
    
    def get_leads(self) -> list:
        return self.leads
# bot.py
import asyncio
from config import Config
from adapters.discord_adapter import DiscordAdapter
from adapters.telegram_adapter import TelegramAdapter
from faq_responder import FAQResponder
from lead_capture import LeadCaptureHandler

class BotFramework:
    def __init__(self):
        self.config = Config()
        self.faq_responder = FAQResponder(self.config.FAQ_FILE)
        self.lead_handler = LeadCaptureHandler(self.config.LEAD_WEBHOOK_URL)
        self.adapter = self._create_adapter()
    
    def _create_adapter(self):
        if self.config.PLATFORM == 'telegram':
            return TelegramAdapter(self.config.TELEGRAM_TOKEN)
        else:
            return DiscordAdapter(self.config.DISCORD_TOKEN)
    
    async def handle_message(self, parsed_message: dict):
        content = parsed_message['content']
        user_id = parsed_message['user_id']
        channel_id = parsed_message['channel_id']
        username = parsed_message['username']
        
        # Check for lead capture keywords
        lead_keywords = ['interested', 'signup', 'contact', 'demo', 'trial']
        is_lead = any(keyword in content.lower() for keyword in lead_keywords)
        
        if is_lead:
            user_info = {
                'user_id': user_id,
                'username': username
            }
            self.lead_handler.capture_lead(user_info, content)
            await self.adapter.send_message(channel_id, "Thanks for your interest! Our team will contact you soon.")
            return
        
        # FAQ response
        answer = self.faq_responder.find_answer(content)
        await self.adapter.send_message(channel_id, answer)
    
    async def run(self):
        await self.adapter.start()

if __name__ == '__main__':
    bot = BotFramework()
    asyncio.run(bot.run())