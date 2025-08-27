class RetryableTask(Exception):
    """Raised when transaction should be retried."""

def _retry_with_delay(task_self, exc, delay_count):
    retry_count = task_self.request.retries  # 0 for first retry, 1 for second, etc.
    if retry_count >= 3:  # already retried 3 times
        print(f"[Fail] Task {task_self.request.id} reached max retries ({task_self.max_retries}) and failed permanently.")
        raise exc
    delay = delay_count[retry_count] if retry_count < len(delay_count) else delay_count[-1]
    print(f"[Retry] Task {task_self.request.id}: attempt {retry_count + 1} failed. Retrying in {delay} seconds.")
    raise task_self.retry(exc=exc, countdown=delay, throw=False)