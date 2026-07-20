# Configure AI models

Use **Admin → Settings → AI Settings** to configure AI providers and models. Changes are saved in the database and normally do not require a redeployment.

> **Important: AppFlowy supports only 1,536-dimensional embeddings.**
>
> Embedding models that return any other dimension are not supported, even if they appear in model discovery.

## Before you begin

Make sure you have:

- A valid AppFlowy commercial license with AI enabled.
- Provider-aware versions of `admin-frontend`, `appflowy-cloud`, and `appflowy-ai`.
- An API key for each provider you want to use.
- Outbound network access from AppFlowy to the provider endpoint.


## 1. Enable AI
![AI settings and provider list](asset/ai-settings.png)

Open **AI Settings** and turn on **Enable AI Features**. When this setting is off, AI features are disabled for everyone.

## 2. Add a provider

Open the **Models** tab and select **Add Provider**.

| Provider        | What to enter                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| OpenAI          | API key. Leave **Base URL** empty for the official OpenAI endpoint. Use the Responses API for official OpenAI models.               |
| Azure OpenAI    | API key, Azure endpoint, and API version. Each model also needs its Azure deployment name.                                          |
| Anthropic       | API key. The base URL can normally be left empty.                                                                                   |
| DeepSeek        | API key and base URL. The base URL is required even if Admin labels it as optional.                                                 |
| Qwen            | API key and base URL. The default DashScope URL is `https://dashscope.aliyuncs.com/compatible-mode/v1`. Qwen uses Chat Completions. |
| Google Gemini   | API key. The base URL can normally be left empty.                                                                                   |
| Custom provider | API key, OpenAI-compatible base URL, and the API type supported by the endpoint.                                                    |

Both the provider and its models must be enabled.

![Add an AI provider](asset/ai-add-provider.png)

## 3. Add a chat model
![Models configured for a provider](asset/ai-provider-models.png)
Expand the provider card and select **Add Model**. You can select a discovered model or use **Add Manually**.

![Select a discovered model](asset/ai-select-model.png)
Enter:

- **Display Name**: the name shown to users.
- **API Model ID**: the exact model ID used by OpenAI, Anthropic, DeepSeek, Qwen, Gemini, or a custom provider.
- **Deployment Name**: the exact Azure deployment name. Azure uses this instead of an API model ID.
- **Enabled**: makes the model available.
- **Set as Default**: makes it the default chat model.

![Configure a chat model](asset/ai-add-model.png)

Save the model, run its test, and confirm that the test passes. The **Available Models (Client View)** section shows which models AppFlowy clients can use.

## 4. Configure an embedding model

AppFlowy supports only these embedding configurations:

| Provider                              | Required model configuration                                           |
| ------------------------------------- | ---------------------------------------------------------------------- |
| OpenAI                                | API Model ID: `text-embedding-3-small`                                 |
| Azure OpenAI                          | Display Name: `text-embedding-3-small`, plus the Azure deployment name |
| Qwen with DashScope                   | API Model ID: `text-embedding-v4`                                      |
| Qwen with a Qwen3-compatible endpoint | API Model ID: `qwen3-embedding` or `qwen3-embedding:latest`            |

All supported configurations produce exactly **1,536 dimensions**.

Models such as `text-embedding-3-large` and `text-embedding-ada-002` are not supported. Custom providers, Anthropic, DeepSeek, and Gemini cannot be used for embeddings.

To activate an embedding model:

1. Open the **Embeddings** tab.
2. Add one of the supported models above.
3. Select **Enabled** and **Set as Default**.
4. Run the model test.
5. Confirm that the test reports `dimension: 1536` and the model shows **Active**.

![Configure an embedding model](asset/ai-embedding-model.png)

### Changing the embedding model

Different embedding models are not interchangeable, even when they all use 1,536 dimensions. After switching models, existing documents must be indexed again. Semantic search results may be incomplete while reindexing is in progress.

Keep `APPFLOWY_INDEXER_ENABLED=true` during this process.

## 5. Configure AI Overview

AI Overview can use a different model from normal chat:

1. Open **Tools → AI Overview**.
2. Select an enabled chat model.
3. Prefer a fast, non-reasoning model.
4. Select **Save AI Overview**.

Select **Use chat default** if AI Overview should follow the default chat model. Changes normally reach Cloud and Search within about 15 seconds.

![Configure the AI Overview model](asset/ai-overview.png)

## 6. Configure web search

Web search lets AI use current information from the web:

1. Open **Tools → Search**.
2. Select a search provider. **DuckDuckGo** is the keyless fallback.
3. Set **Maximum results** between 1 and 10.
4. Select **Enable web search**.
5. Enter a test query and select **Test Search**.
6. Select **Save Search Tool**.

Individual chats and requests must still opt in before AI can use web search.

![Configure web search](asset/ai-web-search.png)

## Important behavior

- Keep one enabled default chat model.
- Keep one active embedding model when semantic search is used.
- A model works only when its provider is enabled and has a valid API key.
- Provider card order changes the order shown to clients; it does not change the default model.
- Before deleting a provider, move the chat default, embedding default, and AI Overview assignment to another provider.
- Environment variables are mainly used to bootstrap a new installation. After initialization, settings saved through Admin are authoritative.

## Troubleshooting

| Problem                                 | What to check                                                                      |
| --------------------------------------- | ---------------------------------------------------------------------------------- |
| AI Settings is missing                  | Check the commercial license and service versions.                                 |
| Model discovery fails                   | Check the API key and endpoint, or use **Add Manually**.                           |
| Model is not visible to clients         | Enable both the provider and model, then check **Available Models (Client View)**. |
| OpenAI-compatible requests fail         | Select the API type supported by the endpoint: Responses or Chat Completions.      |
| DeepSeek fails in AI Overview or Search | Configure an explicit DeepSeek base URL.                                           |
| Embedding test fails                    | Use an exact supported model and confirm it returns `1536` dimensions.             |
| Embedding model shows Standby           | Enable it and select **Set as Default**.                                           |
| Changes are not visible immediately     | Wait about 15 seconds and refresh the client view.                                 |
