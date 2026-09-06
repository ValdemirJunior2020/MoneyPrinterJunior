import { FormEvent, useEffect, useMemo, useState } from 'react';
import { cancelTask, createTask, getTask, retryTask, TaskStatus, uploadAudio } from './api';

const DURATION_OPTIONS = Array.from({ length: 10 }, (_, i) => i + 1);
const NARRATION_STYLES = ['Calm', 'Documentary', 'Warm', 'Inspirational', 'Emotional', 'Dramatic', 'Sermon'] as const;
const SCRIPT_ACTIONS = ['Preserve', 'Rewrite', 'Expand', 'Shorten', 'Improve'] as const;
const STAGES = [
  'Understanding topic', 'Writing script', 'Planning scenes', 'Generating narration', 'Searching media',
  'Downloading media', 'Preparing visuals', 'Generating subtitles', 'Rendering', 'Finalizing', 'Complete',
];

type Mode = 'topic' | 'script';

function App() {
  const [mode, setMode] = useState<Mode>('topic');
  const [topic, setTopic] = useState('');
  const [script, setScript] = useState('');
  const [scriptAction, setScriptAction] = useState<(typeof SCRIPT_ACTIONS)[number]>('Preserve');
  const [duration, setDuration] = useState(5);
  const [style, setStyle] = useState<(typeof NARRATION_STYLES)[number]>('Documentary');
  const [aspect, setAspect] = useState<'16:9' | '9:16'>('16:9');
  const [mediaSource, setMediaSource] = useState<'auto' | 'pexels' | 'wikimedia' | 'internet_archive'>('auto');
  const [transition, setTransition] = useState<'None' | 'Fade' | 'Crossfade' | 'Subtle Zoom'>('Fade');
  const [subtitles, setSubtitles] = useState(true);
  const [subtitleMode, setSubtitleMode] = useState<'sentence' | 'phrase'>('phrase');
  const [font, setFont] = useState('Arial');
  const [fontSize, setFontSize] = useState(46);
  const [position, setPosition] = useState<'top' | 'middle' | 'bottom'>('bottom');
  const [foreground, setForeground] = useState('#FFFFFF');
  const [stroke, setStroke] = useState('#000000');
  const [strokeWidth, setStrokeWidth] = useState(3);
  const [subtitleBackground, setSubtitleBackground] = useState(false);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [musicVolume, setMusicVolume] = useState(0.12);
  const [musicFile, setMusicFile] = useState<File | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  const canGenerate = useMemo(() => mode === 'topic' ? topic.trim().length > 2 : script.trim().length > 10, [mode, topic, script]);

  useEffect(() => {
    if (!task || !['queued', 'running'].includes(task.state)) return;
    const timer = window.setInterval(async () => {
      try {
        setTask(await getTask(task.task_id));
      } catch (err) {
        setLocalError(err instanceof Error ? err.message : String(err));
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [task?.task_id, task?.state]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canGenerate) return;
    setBusy(true);
    setLocalError('');
    try {
      const reference_voice_path = referenceFile ? await uploadAudio(referenceFile) : null;
      const uploadedMusicPath = musicEnabled && musicFile ? await uploadAudio(musicFile) : null;
      const payload = {
        mode,
        topic,
        script,
        script_action: scriptAction,
        duration_minutes: duration,
        narration_style: style,
        aspect,
        media_source: mediaSource,
        transition,
        reference_voice_path,
        subtitles: {
          enabled: subtitles,
          font,
          size: fontSize,
          position,
          foreground_color: foreground,
          stroke_color: stroke,
          stroke_width: strokeWidth,
          background: subtitleBackground,
          mode: subtitleMode,
        },
        music: {
          enabled: musicEnabled,
          volume: musicVolume,
          fade_in: 2,
          fade_out: 3,
          uploaded_path: uploadedMusicPath,
        },
      };
      setTask(await createTask(payload));
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!task) return;
    await cancelTask(task.task_id);
    setTask(await getTask(task.task_id));
  }

  async function retry() {
    if (!task) return;
    setLocalError('');
    setTask(await retryTask(task.task_id));
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">LOCAL AI VIDEO STUDIO</div>
          <h1>Ollama Video Studio</h1>
          <p>Qwen plans it. Chatterbox narrates it. FFmpeg finishes it.</p>
        </div>
        <div className="local-pill">Local-first · qwen3:8b</div>
      </header>

      <form onSubmit={submit} className="workspace">
        <section className="panel editor-panel">
          <div className="mode-tabs" role="tablist" aria-label="Input mode">
            <button type="button" className={mode === 'topic' ? 'active' : ''} onClick={() => setMode('topic')}>Topic</button>
            <button type="button" className={mode === 'script' ? 'active' : ''} onClick={() => setMode('script')}>Script</button>
          </div>

          {mode === 'topic' ? (
            <label className="field grow">
              <span>Topic</span>
              <textarea data-testid="topic-input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="The story of Abraham leaving Ur" />
            </label>
          ) : (
            <>
              <label className="field grow">
                <span>Script</span>
                <textarea data-testid="script-input" value={script} onChange={(e) => setScript(e.target.value)} placeholder="Paste the exact narration you want spoken..." />
              </label>
              <label className="field compact">
                <span>Script handling</span>
                <select value={scriptAction} onChange={(e) => setScriptAction(e.target.value as typeof scriptAction)}>
                  {SCRIPT_ACTIONS.map((item) => <option key={item}>{item}</option>)}
                </select>
                <small>Preserve keeps pasted words unchanged.</small>
              </label>
            </>
          )}
        </section>

        <aside className="panel controls-panel">
          <div className="control-grid">
            <label className="field">
              <span>Duration</span>
              <select data-testid="duration-select" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
                {DURATION_OPTIONS.map((minute) => <option key={minute} value={minute}>{minute} minute{minute > 1 ? 's' : ''}</option>)}
              </select>
            </label>

            <label className="field">
              <span>Narration Style</span>
              <select data-testid="narration-style-select" value={style} onChange={(e) => setStyle(e.target.value as typeof style)}>
                {NARRATION_STYLES.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>

            <label className="field">
              <span>Video Aspect</span>
              <select value={aspect} onChange={(e) => setAspect(e.target.value as typeof aspect)}>
                <option>16:9</option><option>9:16</option>
              </select>
            </label>

            <label className="field">
              <span>Media Source</span>
              <select data-testid="media-source-select" value={mediaSource} onChange={(e) => setMediaSource(e.target.value as typeof mediaSource)}>
                <option value="auto">Auto</option>
                <option value="wikimedia">Wikimedia Commons</option>
                <option value="internet_archive">Internet Archive</option>
                <option value="pexels">Pexels</option>
              </select>
            </label>

            <label className="field">
              <span>Transition</span>
              <select value={transition} onChange={(e) => setTransition(e.target.value as typeof transition)}>
                <option>None</option><option>Fade</option><option>Crossfade</option><option>Subtle Zoom</option>
              </select>
            </label>

            <label className="field file-field">
              <span>Reference Voice (Optional)</span>
              <input data-testid="reference-voice" type="file" accept="audio/wav,audio/mpeg,.wav,.mp3" onChange={(e) => setReferenceFile(e.target.files?.[0] ?? null)} />
            </label>
          </div>

          <details open data-testid="subtitle-controls" className="subpanel">
            <summary>Subtitles</summary>
            <div className="toggle-row">
              <span>Enable subtitles</span>
              <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />
            </div>
            {subtitles && <div className="mini-grid">
              <label>Mode<select value={subtitleMode} onChange={(e) => setSubtitleMode(e.target.value as typeof subtitleMode)}><option value="phrase">Phrase</option><option value="sentence">Sentence</option></select></label>
              <label>Font<input value={font} onChange={(e) => setFont(e.target.value)} /></label>
              <label>Size<input type="number" min="18" max="96" value={fontSize} onChange={(e) => setFontSize(Number(e.target.value))} /></label>
              <label>Position<select value={position} onChange={(e) => setPosition(e.target.value as typeof position)}><option value="bottom">Bottom</option><option value="middle">Middle</option><option value="top">Top</option></select></label>
              <label>Text<input type="color" value={foreground} onChange={(e) => setForeground(e.target.value)} /></label>
              <label>Stroke<input type="color" value={stroke} onChange={(e) => setStroke(e.target.value)} /></label>
              <label>Stroke width<input type="number" min="0" max="10" value={strokeWidth} onChange={(e) => setStrokeWidth(Number(e.target.value))} /></label>
              <label className="check-label">Background<input type="checkbox" checked={subtitleBackground} onChange={(e) => setSubtitleBackground(e.target.checked)} /></label>
            </div>}
          </details>

          <details className="subpanel">
            <summary>Background Music</summary>
            <div className="toggle-row"><span>Enable music</span><input type="checkbox" checked={musicEnabled} onChange={(e) => setMusicEnabled(e.target.checked)} /></div>
            {musicEnabled && <div className="mini-grid">
              <label>Music file<input type="file" accept="audio/*" onChange={(e) => setMusicFile(e.target.files?.[0] ?? null)} /></label>
              <label>Volume<input type="range" min="0" max="0.6" step="0.01" value={musicVolume} onChange={(e) => setMusicVolume(Number(e.target.value))} /></label>
            </div>}
          </details>

          <button data-testid="generate-button" disabled={!canGenerate || busy || task?.state === 'running'} className="generate" type="submit">
            {busy ? 'Preparing…' : 'Generate Video'}
          </button>
        </aside>
      </form>

      {(task || localError) && <section className="panel progress-panel" aria-live="polite">
        {localError && <div className="error-box">{localError}</div>}
        {task && <>
          <div className="progress-head">
            <div><span className="status-dot" /> <strong>{task.stage}</strong>{task.current_scene ? ` · Scene ${task.current_scene}` : ''}</div>
            <div>{task.progress}% · {Math.round(task.elapsed_seconds)}s</div>
          </div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${task.progress}%` }} /></div>
          <div className="stage-strip">{STAGES.map((name) => <span key={name} className={name === task.stage ? 'current' : ''}>{name}</span>)}</div>
          {task.error && <div className="error-box">{task.error}</div>}
          {['queued', 'running'].includes(task.state) && <button type="button" className="cancel" onClick={cancel}>Cancel Task</button>}
          {task.state === 'failed' && <button type="button" className="cancel" onClick={retry}>Retry Task</button>}
          {task.state === 'complete' && task.output_url && <div className="result-box">
            <video controls src={task.output_url} />
            <a href={task.output_url} download>Download MP4</a>
          </div>}
        </>}
      </section>}
      <footer className="footer-note">When Pexels media is used, attribution is saved with the task. <a href="https://www.pexels.com" target="_blank" rel="noreferrer">Photos and videos provided by Pexels</a>.</footer>
    </main>
  );
}

export default App;
