import React, { useState } from "react";
import "./Homepage.css";

export default function HomePage() {
  const [fileUploaded, setFileUploaded] = useState(false);
  const [folderUploaded, setFolderUploaded] = useState(false);
  const [folderContents, setFolderContents] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleFileUpload = (event) => {
    const files = event.target.files;
    if (files.length > 0) {
      setSelectedFiles(Array.from(files));
      setFileUploaded(true);
      setFolderUploaded(false);
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
    } else {
      alert("Tidak ada file dengan ekstensi .js atau .py yang ditemukan.");
      setFolderUploaded(false);
    }
  };

  const handleUploadToBackend = async () => {
    if (selectedFiles.length === 0) {
        alert("Tidak ada file yang dipilih.");
        return;
    }

    setIsUploading(true);
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append("files", file));

    // Cek total ukuran file sebelum upload
    let totalSize = selectedFiles.reduce((acc, file) => acc + file.size, 0);
    console.log("Total file size:", (totalSize / (1024 * 1024)).toFixed(2), "MB");

    try {
        const response = await fetch("http://localhost:5000/upload", {
            method: "POST",
            body: formData,
        });

        // Cek jika respons bukan JSON (karena error 413 biasanya mengembalikan halaman HTML)
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            throw new Error("Server mengembalikan respon yang tidak valid. Periksa batas ukuran upload.");
        }

        const result = await response.json();
        console.log("Response dari backend:", result);
        setUploadStatus(result);

        if (result.saved_files && result.saved_files.length > 0) {
            alert("Upload berhasil!");
        } else {
            alert("Upload gagal: " + (result.error || "Terjadi kesalahan."));
        }
    } catch (error) {
        console.error("Upload gagal:", error);
        alert("Terjadi kesalahan saat mengupload file.");
    }
    setIsUploading(false);
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
              <li key={index}>{file.name}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
