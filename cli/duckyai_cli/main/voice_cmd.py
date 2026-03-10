"""duckyai voice — real-time voice conversation command."""

import os
import sys
import asyncio
import click


@click.command("voice")
@click.option("--endpoint", envvar="AZURE_VOICELIVE_ENDPOINT", default=None, help="Azure Voice Live endpoint")
@click.option("--api-key", envvar="AZURE_VOICELIVE_API_KEY", default=None, help="Azure API key (or use Entra ID)")
@click.option("--model", default="gpt-4o-realtime-preview", help="Voice Live model")
@click.option("--voice", default="en-US-Ava:DragonHDLatestNeural", help="Voice name")
@click.option("--use-entra", is_flag=True, default=False, help="Use Azure Entra ID auth instead of API key")
def voice_command(endpoint, api_key, model, voice, use_entra):
    """Start a real-time voice conversation with DuckyAI.

    \b
    Uses Azure Voice Live SDK for speech-to-speech conversation.
    Speak naturally — voice activity detection handles turn-taking.

    \b
    Examples:
        duckyai voice                              # Uses env vars for auth
        duckyai voice --use-entra                  # Azure Entra ID auth
        duckyai voice --api-key YOUR_KEY           # API key auth
        duckyai voice --voice alloy                # OpenAI voice
    """
    # Validate audio system
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_ok = any(d['max_input_channels'] > 0 for d in devices if isinstance(d, dict))
        output_ok = any(d['max_output_channels'] > 0 for d in devices if isinstance(d, dict))
        if not input_ok:
            click.echo("❌ No microphone found. Please check your audio input device.")
            sys.exit(1)
        if not output_ok:
            click.echo("❌ No speakers found. Please check your audio output device.")
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Audio system check failed: {e}")
        click.echo("Install sounddevice: pip install sounddevice")
        sys.exit(1)

    # Resolve credentials
    if not endpoint:
        click.echo("❌ Azure Voice Live endpoint required.")
        click.echo("Set AZURE_VOICELIVE_ENDPOINT env var or use --endpoint")
        sys.exit(1)

    if use_entra:
        try:
            from azure.identity.aio import AzureCliCredential
            credential = AzureCliCredential()
        except ImportError:
            click.echo("❌ azure-identity not installed. Run: pip install azure-identity")
            sys.exit(1)
    elif api_key:
        from azure.core.credentials import AzureKeyCredential
        credential = AzureKeyCredential(api_key)
    else:
        click.echo("❌ Authentication required. Use --api-key or --use-entra")
        sys.exit(1)

    # Build DuckyAI system prompt
    instructions = (
        "You are DuckyAI, a personal knowledge management assistant. "
        "You help the user manage their vault of notes, meetings, tasks, and knowledge. "
        "You can search their vault, summarize meetings, create tasks, and answer questions "
        "about their work. Be concise and conversational. "
        "When the user asks about meetings, chats, or tasks, describe what you find clearly."
    )

    # Run voice session
    from ..voice.realtime import run_voice_session

    try:
        asyncio.run(run_voice_session(
            endpoint=endpoint,
            credential=credential,
            model=model,
            voice=voice,
            instructions=instructions,
        ))
    except KeyboardInterrupt:
        click.echo("\n👋 Voice session ended. Goodbye!")
    except Exception as e:
        click.echo(f"❌ Voice session failed: {e}")
        sys.exit(1)
