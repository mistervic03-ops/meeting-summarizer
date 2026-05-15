import React from "react";

interface FilePickerProps {
  accept: string;
  file: File | null;
  label: string;
  onChange: (file: File | null) => void;
}

export function FilePicker({ accept, file, label, onChange }: FilePickerProps) {
  return (
    <label className="file-picker">
      <span>{label}</span>
      <input
        accept={accept}
        type="file"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
      <strong>{file ? file.name : "파일을 선택해 주세요"}</strong>
    </label>
  );
}
