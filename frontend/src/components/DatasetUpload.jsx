import { useState, useRef } from 'react';
import { uploadDataset } from '../services/api';

export default function DatasetUpload({ onUploadSuccess }) {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    if (!file.name.endsWith('.csv')) {
      setError("Please upload a valid CSV file.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await uploadDataset(file);
      setSuccessMsg(result.message);
      if (onUploadSuccess) onUploadSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <div className="w-full rounded-2xl border p-5 flex items-center gap-5 shadow-lg glass-panel bg-indigo-950/20 border-indigo-500/20 shadow-indigo-500/5 mb-8">
      <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 bg-indigo-500/20 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
        📊
      </div>
      <div className="flex-1">
        <h3 className="text-lg font-bold mb-1 text-indigo-300 drop-shadow-md">
          Provide Your Data
        </h3>
        <p className="text-sm text-indigo-100/60">
          Upload a CSV file to instantly create a database table. The RAG AI will automatically analyze the columns and prepare it for natural language querying.
        </p>
        
        {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
        {successMsg && <p className="text-emerald-400 text-sm mt-2">{successMsg}</p>}
      </div>
      
      <div>
        <input 
          type="file" 
          accept=".csv" 
          className="hidden" 
          ref={fileInputRef}
          onChange={handleFileChange}
        />
        <button 
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors font-medium text-sm flex items-center gap-2 disabled:opacity-50"
        >
          {isUploading ? (
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          ) : 'Upload CSV'}
        </button>
      </div>
    </div>
  );
}
