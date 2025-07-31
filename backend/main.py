import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import openai

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")

class PodEvent(BaseModel):
    type: str
    name: str
    namespace: str
    status: str
    reason: str
    timestamp: str

# Jednostruka memorija za primljene evente i AI odgovore
stored_events = []

def ask_openai(prompt: str) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Kubernetes expert assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI error: {str(e)}"

@app.post("/api/events")
async def receive_event(event: PodEvent):
    prompt = (
        f"A Kubernetes Pod named `{event.name}` in namespace `{event.namespace}` is in status `{event.status}`. "
        f"Reason: {event.reason}. "
        "What is the likely cause and how to fix it? Respond briefly."
    )
    fix_suggestion = ask_openai(prompt)

    record = {
        "name": event.name,
        "namespace": event.namespace,
        "status": event.status,
        "reason": event.reason,
        "timestamp": event.timestamp,
        "suggested_fix": fix_suggestion
    }
    stored_events.append(record)
    return {"message": "Event received", "suggested_fix": fix_suggestion}

@app.get("/api/issues")
async def get_issues():
    return stored_events
