from datetime import timedelta


def format_timestamp_srt(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# segments: [{'word':'hello','start_time':0.1,'end_time':0.5}, ...]
def group_segments_to_lines(segments, max_words=10, max_duration=5.0):
    lines = []
    if not segments:
        return lines
    cur_words = []
    start = segments[0]['start_time']
    for seg in segments:
        cur_words.append(seg['word'])
        duration = seg['end_time'] - start
        if len(cur_words) >= max_words or duration >= max_duration:
            lines.append({'start': start, 'end': seg['end_time'], 'text': ' '.join(cur_words)})
            cur_words = []
            start = seg['end_time']
    if cur_words:
        lines.append({'start': start, 'end': segments[-1]['end_time'], 'text': ' '.join(cur_words)})
    return lines


def export_srt(segments):
    lines = group_segments_to_lines(segments)
    parts = []
    for i, l in enumerate(lines, start=1):
        parts.append(str(i))
        parts.append(f"{format_timestamp_srt(l['start'])} --> {format_timestamp_srt(l['end'])}")
        parts.append(l['text'])
        parts.append('')
    return '\n'.join(parts)


def export_vtt(segments):
    lines = group_segments_to_lines(segments)
    parts = ['WEBVTT', '']
    for l in lines:
        parts.append(f"{format_timestamp_vtt(l['start'])} --> {format_timestamp_vtt(l['end'])}")
        parts.append(l['text'])
        parts.append('')
    return '\n'.join(parts)
