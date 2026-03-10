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
@click.option("--open-mic", is_flag=True, default=False, help="Use open-mic mode with VAD (default: push-to-talk)")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose logging")
def voice_command(endpoint, api_key, model, voice, use_entra, open_mic, verbose):
    """Start a real-time voice conversation with DuckyAI.

    \b
    Default: Push-to-talk — hold Space to talk, release to send.
    Use --open-mic for hands-free with voice activity detection.

    \b
    Examples:
        duckyai voice --use-entra                  # Push-to-talk (default)
        duckyai voice --use-entra --open-mic       # Open mic with VAD
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

    # Set up logging
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    else:
        import logging
        logging.basicConfig(level=logging.WARNING)

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
        "You are DuckyAI, a personal knowledge management voice assistant. "
        "You help the user manage their vault of notes, meetings, tasks, and knowledge. "
        "You have tools available to search their vault, read notes, get today's meetings and tasks, "
        "create tasks, sync Teams chats and meetings, and read specific notes. "
        "Use these tools when the user asks about their work, meetings, or tasks. "
        "Be concise and conversational — this is a voice interface, so keep responses brief and natural. "
        "When reporting search results or meeting details, summarize the key points rather than reading raw markdown."
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
            push_to_talk=not open_mic,
        ))
    except KeyboardInterrupt:
        click.echo("\n👋 Voice session ended. Goodbye!")
    except Exception as e:
        click.echo(f"❌ Voice session failed: {e}")
        sys.exit(1)
