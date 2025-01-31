import React, { useState } from "react";
import "./Homepage.css";

export default function HomePage() {
  const [fileUploaded, setFileUploaded] = useState(false);
  const [folderUploaded, setFolderUploaded] = useState(false);
  const [folderContents, setFolderContents] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState({
    uploaded: false,
    analyzed: false,
    message: ""
  });
  const [isUploading, setIsUploading] = useState(false);
  const [fileProgress, setFileProgress] = useState({}); // Track progress per file

  const CHUNK_SIZE = 1024 * 1024 * 500; //500MB

  const handleFileUpload = (event) => {
    const files = event.target.files;
    if (files.length > 0) {
      setSelectedFiles(Array.from(files));
      setFileUploaded(true);
      setFolderUploaded(false);
      console.log(`Selected ${files.length} files for upload`);
    }
  };

  const handleFolderUpload = (event) => {
    const files = event.target.files;
    let fileList = [];
    for (let i = 0; i < files.length; i++) {
      if (files[i].name.endsWith(".js") || files[i].name.endsWith(".py")) {
        fileList.push(files[i]);
      }
    }
    if (fileList.length > 0) {
      setSelectedFiles(fileList);
      setFolderUploaded(true);
      setFileUploaded(false);
      setFolderContents(fileList.map(file => file.name));
      console.log(`Selected ${fileList.length} files from folder`);
    } else {
      console.warn("No .js or .py files found in folder");
      alert("Tidak ada file dengan ekstensi .js atau .py yang ditemukan.");
      setFolderUploaded(false);
    }
  };

  const uploadChunk = async (file, start, chunk, sessionId) => {
    const formData = new FormData();
    formData.append("file", chunk);
    formData.append("sessionId", sessionId);
    formData.append("start", start);
    formData.append("total_size", file.size);
    formData.append("filename", file.name);

    console.log(`Uploading chunk for ${file.name}: ${start}-${start + chunk.size} of ${file.size}`);

    const response = await fetch("http://localhost:5000/upload-chunk", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload chunk failed: ${response.statusText}`);
    }
    const result = await response.json();
    console.log(`Chunk upload response:`, result);

    // Update progress for this specific file
    const progress = Math.min(Math.round((start + chunk.size) / file.size * 100), 100);
    setFileProgress((prevProgress) => ({
      ...prevProgress,
      [file.name]: progress, // Update progress for this file
    }));

    return result;
  };

  const handleUploadToBackend = async () => {
    if (selectedFiles.length === 0) {
      console.warn("No files selected for upload");
      alert("Tidak ada file yang dipilih.");
      return;
    }

    setIsUploading(true);
    const sessionId = Date.now().toString();
    console.log(`Starting upload session: ${sessionId}`);

    try {
      for (const file of selectedFiles) {
        console.log(`Processing file: ${file.name} (${file.size} bytes)`);
        let start = 0;
        while (start < file.size) {
          const chunk = file.slice(start, start + CHUNK_SIZE);
          await uploadChunk(file, start, chunk, sessionId);
          start += CHUNK_SIZE;
        }
        // Once the file is uploaded, update progress to 100%
        setFileProgress((prevProgress) => ({
          ...prevProgress,
          [file.name]: 100,
        }));
        console.log(`Completed uploading file: ${file.name}`);
      }

      console.log("All files uploaded, finalizing...");
      const finalizeResponse = await fetch("http://localhost:5000/finalize-upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sessionId,
          files: selectedFiles.map(f => ({ 
            filename: f.name, 
            size: f.size 
          }))
        }),
      });

      if (!finalizeResponse.ok) {
        throw new Error("Failed to finalize upload");
      }

      const result = await finalizeResponse.json();
      console.log("Upload finalized:", result);
      
      setUploadStatus({
        uploaded: true,
        analyzed: false,
        message: result.message
      });

      alert("Upload berhasil!");
    } catch (error) {
      console.error("Upload error:", error);
      setUploadStatus({
        uploaded: false,
        analyzed: false,
        message: error.message
      });
      alert("Terjadi kesalahan saat mengupload file.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="container-homepage">
      <nav className="navbar">HauntAI</nav>
      <div className="upload-container">
        <h2>Upload File or Folder</h2>
        <p className="upload-limit">Maksimum ukuran file: 1GB</p>
        <div className="upload-options">
          <div className="upload-box">
            <label className={`upload-label ${folderUploaded ? "disabled" : ""}`}>
              Upload File
              <input type="file" multiple onChange={handleFileUpload} disabled={folderUploaded} />
            </label>
          </div>
          <div className="upload-box">
            <label className={`upload-label ${fileUploaded ? "disabled" : ""}`}>
              Upload Folder
              <input type="file" webkitdirectory="" directory="" multiple onChange={handleFolderUpload} disabled={fileUploaded} />
            </label>
          </div>
        </div>
        <button className="upload-button" onClick={handleUploadToBackend}>{isUploading ? "Uploading..." : "Upload"}</button>
      </div>

      {selectedFiles.length > 0 && (
        <div className="folder-content-container">
          <h3>File yang Akan Diupload:</h3>
          <ul>
            {selectedFiles.map((file, index) => (
              <li key={index}>
                {file.name}
                {fileProgress[file.name] !== undefined && ( // Ensure we display progress only if available
                  <span style={{ marginLeft: "10px", fontSize: "12px" }}>
                    {fileProgress[file.name]}% {/* Displaying progress beside the filename */}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
