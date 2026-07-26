"""
target.py - adapters that let the red-teamer talk to YOUR product.

Pick the one that matches how your product is reachable:

  HTTPTarget          - your product exposes an HTTP endpoint you can POST to.
  OpenAICompatTarget  - it speaks the OpenAI chat/completions format.
  CallableTarget      - it's a local Python function (e.g. your mini-GPT's
                        generate(prompt) or your RAG chain's .invoke()).
  ManualFileTarget    - it has NO API. You run the prompts by hand, paste the
                        responses into a JSON file, and grade those. This is the
                        response-grader fallback - still fully works.

Every target carries `model_family` so the runner can enforce Judge != Target.
"""

import json


class BaseTarget:
    model_family = "other"

    def ask(self, prompt: str, context=None) -> str:
        raise NotImplementedError


class HTTPTarget(BaseTarget):
    def __init__(self, url, response_path=("response",), headers=None,
                 payload_key="message", model_family="other", timeout=60):
        self.url, self.headers = url, headers or {}
        self.response_path, self.payload_key = response_path, payload_key
        self.model_family, self.timeout = model_family, timeout

    def ask(self, prompt, context=None):
        import requests
        r = requests.post(self.url, headers=self.headers,
                          json={self.payload_key: prompt}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        for key in self.response_path:            # walk e.g. ("data","answer")
            data = data[key]
        return data if isinstance(data, str) else json.dumps(data)


class OpenAICompatTarget(BaseTarget):
    """For products that ARE an OpenAI-style chat endpoint (incl. your own wrapper)."""
    def __init__(self, model, base_url=None, api_key_env="TARGET_API_KEY",
                 system=None, model_family="gpt"):
        import os
        from openai import OpenAI
        self.client = OpenAI(api_key=os.environ[api_key_env], base_url=base_url)
        self.model, self.system, self.model_family = model, system, model_family

    def ask(self, prompt, context=None):
        msgs = ([{"role": "system", "content": self.system}] if self.system else [])
        msgs.append({"role": "user", "content": prompt})
        r = self.client.chat.completions.create(model=self.model, messages=msgs)
        return r.choices[0].message.content


class CallableTarget(BaseTarget):
    """
    Wrap any local Python callable. Examples:
        CallableTarget(lambda p: my_rag_chain.invoke(p), model_family="claude")
        CallableTarget(mini_gpt_generate, model_family="other")
    """
    def __init__(self, fn, model_family="other"):
        self.fn, self.model_family = fn, model_family

    def ask(self, prompt, context=None):
        out = self.fn(prompt)
        return out if isinstance(out, str) else str(out)


class ManualFileTarget(BaseTarget):
    """
    No-API fallback. Two-step:
      1) call .export_prompts(path, probes) -> writes a JSON stub with empty
         "response" fields. You run each prompt through your product by hand and
         paste its answer in.
      2) load the filled file; ask() returns the response you pasted, keyed by
         prompt id.
    """
    def __init__(self, filled_path=None, model_family="other"):
        self.model_family = model_family
        self.answers = {}
        if filled_path:
            with open(filled_path) as f:
                for row in json.load(f):
                    self.answers[row["id"]] = row["response"]
        self._by_prompt = {}

    @staticmethod
    def export_prompts(path, probes):
        stub = [{"id": p["id"], "prompt": p["prompt"], "response": ""} for p in probes]
        with open(path, "w") as f:
            json.dump(stub, f, indent=2)
        return path

    def bind(self, probe_id):
        self._current = probe_id

    def ask(self, prompt, context=None):
        # relies on runner calling bind() first; falls back to prompt-text match
        pid = getattr(self, "_current", None)
        if pid and pid in self.answers:
            return self.answers[pid]
        raise KeyError("No pasted response for this probe; fill the export file first.")
