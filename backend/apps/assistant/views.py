"""
Staff assistant endpoints (F21).

    GET  /api/v1/assistant/status/   can it answer right now
    POST /api/v1/assistant/ask/      one question, answered as a stream

Every active staff member may ask: the index holds nothing restricted to
some roles (knowledge.py). Nothing is stored. The conversation stays in
the browser and comes back as history with each question.

The answer is newline-delimited JSON, because on a laptop CPU a reply
takes long enough that a person needs to watch it being written:

    {"type": "sources", "sources": [...]}
    {"type": "token", "text": "..."}          repeated
    {"type": "done"}   or   {"type": "error", "message": "..."}
"""

import json

from django.http import StreamingHttpResponse
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import ollama
from .answers import (NO_PRICES, NOT_IN_NOTES, asks_about_prices, build_messages,
                      correction_note, describe_source, find_notes)
from .models import KnowledgeChunk

MAX_QUESTION_CHARS = 1000
MAX_TURN_CHARS = 4000
MAX_HISTORY_TURNS = 6

OFFLINE_MESSAGE = "The assistant is offline. Ask an administrator to start Ollama."
BROKE_OFF_MESSAGE = "The assistant stopped before finishing. Please ask again."


class AssistantOffline(APIException):
    status_code = 503
    default_detail = OFFLINE_MESSAGE


class AssistantThrottle(UserRateThrottle):
    """The model runs on one machine, and every question occupies it."""

    scope = "assistant"


class TurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=MAX_TURN_CHARS)


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=MAX_QUESTION_CHARS)
    history = TurnSerializer(many=True, required=False, max_length=MAX_HISTORY_TURNS)


def event(**fields):
    return json.dumps(fields, ensure_ascii=False) + "\n"


def stream_answer(messages, sources):
    yield event(type="sources", sources=sources)
    answer = []
    try:
        for text in ollama.chat(messages):
            answer.append(text)
            yield event(type="token", text=text)
    except ollama.OllamaUnavailable:
        yield event(type="error", message=BROKE_OFF_MESSAGE)
        return

    # Added at the end, because the answer is already on screen by now.
    note = correction_note("".join(answer))
    if note:
        yield event(type="token", text=note)
    yield event(type="done")


def stream_fixed_reply(text):
    yield event(type="sources", sources=[])
    yield event(type="token", text=text)
    yield event(type="done")


def ndjson(events):
    response = StreamingHttpResponse(events, content_type="application/x-ndjson")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"    # a proxy must not hold the words back
    return response


class AskView(APIView):
    throttle_classes = [AssistantThrottle]

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        history = serializer.validated_data.get("history", [])

        if asks_about_prices(question):
            return ndjson(stream_fixed_reply(NO_PRICES))

        # Searched before the response starts, so an offline server is a
        # plain 503 and not a broken stream.
        try:
            notes = find_notes(question, history)
        except ollama.OllamaUnavailable as exc:
            raise AssistantOffline() from exc

        if not notes:
            return ndjson(stream_fixed_reply(NOT_IN_NOTES))

        messages = build_messages(request.user, question, history, notes)
        return ndjson(stream_answer(messages, [describe_source(note) for note in notes]))


class StatusView(APIView):
    def get(self, request):
        return Response({"ready": not (problem := self.problem()), "problem": problem})

    def problem(self):
        try:
            missing = ollama.missing_models()
        except ollama.OllamaUnavailable:
            return OFFLINE_MESSAGE
        if missing:
            return f"The assistant is missing a model: {', '.join(missing)}. Ask an administrator."
        if not KnowledgeChunk.objects.exists():
            return "The assistant has no notes loaded yet. Ask an administrator to run index_knowledge."
        return ""
