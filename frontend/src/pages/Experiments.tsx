import { useState, type ChangeEvent } from 'react';
import { UploadCloud, FileVideo, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { api, toApiError } from '../lib/api';
import { MESSAGES } from '../lib/messages';
import { confidencePct, formatBytes } from '../lib/format';
import { useSystemStatus } from '../hooks/useSystemStatus';
import type { ProcessResponse, UploadResponse } from '../types/api';

export default function Experiments() {
  const { online, status } = useSystemStatus();
  const modelReady = online && !!status?.model_ready;
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [uploadedData, setUploadedData] = useState<UploadResponse | null>(null);
  const [processData, setProcessData] = useState<ProcessResponse | null>(null);

  const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov'];
  const MAX_SIZE_MB = 500;
  const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    setUploadedData(null);
    setProcessData(null);

    const selectedFile = e.target.files?.[0];
    if (!selectedFile) {
      setFile(null);
      return;
    }

    const ext = '.' + selectedFile.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setErrorMessage(`Invalid format '${ext}'. Only MP4, AVI, and MOV files are allowed.`);
      setFile(null);
      return;
    }

    if (selectedFile.size > MAX_SIZE_BYTES) {
      const sizeMB = (selectedFile.size / (1024 * 1024)).toFixed(1);
      setErrorMessage(`File size (${sizeMB} MB) exceeds the maximum allowed limit of ${MAX_SIZE_MB} MB.`);
      setFile(null);
      return;
    }

    setFile(selectedFile);
  };

  const handleProcessVideo = async () => {
    if (!file) return;

    setUploading(true);
    setProcessing(false);
    setErrorMessage(null);
    setSuccessMessage(null);
    setUploadedData(null);
    setProcessData(null);

    // 1. Upload
    let uploadRes: UploadResponse;
    try {
      uploadRes = await api.uploadVideo(file);
      setUploadedData(uploadRes);
    } catch (err) {
      setUploading(false);
      setErrorMessage(toApiError(err).message);
      return;
    }

    setUploading(false);

    // 2. Process Video using returned video_id
    setProcessing(true);
    try {
      const result = await api.processVideo(uploadRes.video_id);
      setProcessData(result);
      setSuccessMessage(
        result.events_count > 0
          ? `Processing complete for ${result.video_id}: ${result.events_count} activity events detected.`
          : `Processing complete for ${result.video_id}, but no people were detected, so no activity events were produced.`,
      );
    } catch (err) {
      const e = toApiError(err);
      setErrorMessage(
        e.kind === 'offline'
          ? 'Lost connection to the backend during processing. Check that it is still running.'
          : `${MESSAGES.processingFailed} (${e.message})`,
      );
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-deep-blue">Experiments</h1>
      </div>

      <div className="bg-white rounded-2xl p-8 border border-soft-blue shadow-sm space-y-6">
        <h3 className="text-lg font-bold text-deep-blue mb-2">Upload & Process Experiment Video</h3>
        
        <div className="border-2 border-dashed border-soft-blue rounded-xl p-8 flex flex-col items-center justify-center text-center hover:bg-ice-blue/50 transition-colors">
          <div className="bg-ice-blue p-4 rounded-full mb-4">
            <UploadCloud className="w-8 h-8 text-sky-blue" />
          </div>
          <h4 className="text-brand-primary font-medium mb-1">Select video file to upload</h4>
          <p className="text-sm text-brand-secondary mb-6">Supported formats: MP4, AVI, MOV (Max size: 500MB)</p>
          
          <input 
            type="file" 
            accept=".mp4,.avi,.mov,video/mp4,video/x-msvideo,video/quicktime"
            onChange={handleFileChange}
            className="hidden" 
            id="video-upload" 
          />
          <label 
            htmlFor="video-upload" 
            className="cursor-pointer bg-white border border-soft-blue px-6 py-2 rounded-lg text-sm font-medium text-brand-primary hover:bg-ice-blue transition-colors shadow-sm"
          >
            Select Video
          </label>
        </div>

        {file && (
          <div className="p-4 bg-ice-blue rounded-xl border border-soft-blue flex items-center justify-between">
            <div className="flex items-center gap-3">
              <FileVideo className="w-6 h-6 text-sky-blue" />
              <div>
                <p className="text-sm font-medium text-brand-primary">{file.name}</p>
                <p className="text-xs text-brand-secondary">{formatBytes(file.size)}</p>
              </div>
            </div>
            <button 
              onClick={handleProcessVideo}
              disabled={uploading || processing || !modelReady}
              title={!modelReady ? (online ? MESSAGES.modelMissing : MESSAGES.backendOffline) : undefined}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-white shadow-sm transition-colors ${
                uploading || processing || !modelReady ? 'bg-brand-secondary cursor-not-allowed' : 'bg-brand-success hover:bg-green-600'
              }`}
            >
              {(uploading || processing) && <Loader2 className="w-4 h-4 animate-spin" />}
              {uploading ? 'Uploading Video...' : processing ? 'Processing Video...' : 'Process Video'}
            </button>
          </div>
        )}

        {/* Error Notification */}
        {errorMessage && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-brand-alert flex items-start gap-3">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-sm">Upload / Processing Error</p>
              <p className="text-sm text-red-700">{errorMessage}</p>
            </div>
          </div>
        )}

        {/* Success Notification */}
        {successMessage && (
          <div className="p-4 rounded-xl bg-green-50 border border-green-200 text-brand-success flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-sm">Success</p>
              <p className="text-sm text-green-700">{successMessage}</p>
              {uploadedData && (
                <p className="text-xs text-green-600 mt-1">
                  Video ID: <span className="font-mono font-bold">{uploadedData.video_id}</span> | Saved file: {uploadedData.filename} ({formatBytes(uploadedData.file_size)})
                </p>
              )}
            </div>
          </div>
        )}

        {/* Processed Events Preview */}
        {processData && processData.results.length > 0 && (
          <div className="mt-6 border border-soft-blue rounded-xl p-4 bg-white space-y-3">
            <h4 className="font-bold text-deep-blue text-sm">Extracted Activity Events (Video ID: {processData.video_id})</h4>
            <div className="divide-y divide-soft-blue/50">
              {processData.results.map((evt, idx) => (
                <div key={idx} className="py-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-brand-primary">{evt.person_id}</span>
                  <span className="bg-ice-blue px-2.5 py-1 rounded text-sky-blue font-semibold">{evt.activity}</span>
                  <span className="text-xs text-brand-secondary">{evt.start} - {evt.end}</span>
                  <span className="text-xs font-mono text-gray-500">{confidencePct(evt.confidence)}% conf</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

