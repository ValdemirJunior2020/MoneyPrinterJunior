export type TaskStatus = {
  task_id: string;
  state: 'queued' | 'running' | 'cancelled' | 'failed' | 'complete';
  progress: number;
  stage: string;
  current_scene?: number | null;
  elapsed_seconds: number;
  error?: string | null;
  output_url?: string | null;
};

export async function uploadAudio(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/api/uploads', { method: 'POST', body: form });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  return data.path;
}

export async function createTask(payload: unknown): Promise<TaskStatus> {
  const response = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  const response = await fetch(`/api/tasks/${taskId}`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function cancelTask(taskId: string): Promise<void> {
  const response = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
  if (!response.ok) throw new Error(await response.text());
}


export async function retryTask(taskId: string): Promise<TaskStatus> {
  const response = await fetch(`/api/tasks/${taskId}/retry`, { method: 'POST' });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
