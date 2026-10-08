import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# ApiGo

## Overview

| Property | Details |
|-------|-------|
| Description | ApiGo is an AI model API aggregation platform with OpenAI-compatible chat and responses endpoints. |
| Provider Route on LiteLLM | `apigo/` |
| Link to Provider Doc | [ApiGo ↗](https://vip.apigo.ai/doc) |
| Base URL | `https://vip.apigo.ai/v1` |
| Supported Operations | [`/chat/completions`](#sample-usage), [`/responses`](#responses-api) |

<br />
<br />

https://vip.apigo.ai/doc

**We support ApiGo OpenAI-compatible models. Set `apigo/` as the prefix when sending completion requests.**

## Required Variables

```python showLineNumbers title="Environment Variables"
os.environ["APIGO_API_KEY"] = ""  # your ApiGo API key
```

You can override the base URL with:

```python showLineNumbers title="Optional Base URL"
os.environ["APIGO_API_BASE"] = "https://vip.apigo.ai/v1"
```

## Usage - LiteLLM Python SDK

### Non-streaming

```python showLineNumbers title="ApiGo Non-streaming Completion"
import os
from litellm import completion

os.environ["APIGO_API_KEY"] = ""  # your ApiGo API key

response = completion(
    model="apigo/gpt-4o",
    messages=[{"role": "user", "content": "Hello from LiteLLM"}],
)

print(response)
```

### Streaming

```python showLineNumbers title="ApiGo Streaming Completion"
import os
from litellm import completion

os.environ["APIGO_API_KEY"] = ""  # your ApiGo API key

response = completion(
    model="apigo/gpt-4o",
    messages=[{"role": "user", "content": "Hello from LiteLLM"}],
    stream=True,
)

for chunk in response:
    print(chunk)
```

## Responses API

```python showLineNumbers title="ApiGo Responses API"
import os
import litellm

os.environ["APIGO_API_KEY"] = ""  # your ApiGo API key

response = litellm.responses(
    model="apigo/gpt-4o",
    input="Hello from LiteLLM",
)

print(response)
```

## Usage - LiteLLM Proxy

Add the following to your LiteLLM Proxy configuration file:

```yaml showLineNumbers title="config.yaml"
model_list:
  - model_name: apigo-gpt-4o
    litellm_params:
      model: apigo/gpt-4o
      api_key: os.environ/APIGO_API_KEY
```

Start your LiteLLM Proxy server:

```bash showLineNumbers title="Start LiteLLM Proxy"
litellm --config config.yaml

# RUNNING on http://0.0.0.0:4000
```

<Tabs>
<TabItem value="openai-sdk" label="OpenAI SDK">

```python showLineNumbers title="ApiGo via Proxy"
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000",
    api_key="your-proxy-api-key",
)

response = client.chat.completions.create(
    model="apigo-gpt-4o",
    messages=[{"role": "user", "content": "hello from litellm"}],
)

print(response.choices[0].message.content)
```

</TabItem>
</Tabs>
