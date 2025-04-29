import React, { useState } from "react";
import "./Homepage.css";

export default function HomePage() {
  const [fileUploaded, setFileUploaded] = useState(false);
  const [folderUploaded, setFolderUploaded] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState({
    uploaded: false,
    analyzed: false,
    message: "",
    analysisResults: [],
  });
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [fileProgress, setFileProgress] = useState({});
  const [analysisProgress, setAnalysisProgress] = useState({});
  const [showGlobalTooltip, setShowGlobalTooltip] = useState(false);

  // File lebih dari 30MB akan dipecah menjadi chunk
  const CHUNK_SIZE = 1024 * 1024 * 10; // 30MB chunk size

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
    let fileCount = {}; // Objek untuk menyimpan jumlah file dengan nama yang sama

    for (let i = 0; i < files.length; i++) {
      if (files[i].name.endsWith(".js") || files[i].name.endsWith(".py")|| files[i].name.endsWith(".php") || files[i].name.endsWith(".yaml") || files[i].name.endsWith(".ts") || files[i].name.endsWith(".env") || files[i].name === ".env" || files[i].name.startsWith(".env") || files[i].name.endsWith(".json") ||  files[i].name.endsWith(".yml")) {
        let fileName = files[i].name;
        // Jika file dengan nama yang sama sudah ada, tambahin angka
        if (fileCount[fileName]) {
          let count = fileCount[fileName];
          fileCount[fileName]++;
          let nameParts = fileName.split(".");
          let newFileName = `${nameParts[0]}(${count}).${nameParts.slice(1).join(".")}`;

          let renamedFile = new File([files[i]], newFileName, { type: files[i].type });
          fileList.push(renamedFile);
        } else {
          fileCount[fileName] = 1;
          fileList.push(files[i]);
        }
      }
    }

    if (fileList.length > 0) {
      setSelectedFiles(fileList);
      setFolderUploaded(true);
      setFileUploaded(false);
      console.log(`Selected ${fileList.length} files from folder`, fileList);
    } else {
      console.warn("No .js, .py, .json, .env files found in folder");
      alert("Tidak ada file dengan ekstensi .js, .py, .json, .env, .php, yaml, .ts yang ditemukan.");
      setFolderUploaded(false);
    }
  };

  const addLineNumbersToFile = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const fileContent = reader.result;
        const lines = fileContent.split("\n");

        // Menambahkan nomor baris
        const linesWithNumbers = lines.map((line, index) => {
          return `${index + 1}: ${line}`;
        });

        const newContent = linesWithNumbers.join("\n");
        const newFile = new Blob([newContent], { type: file.type });

        resolve(newFile); // Return the new file with line numbers added
      };
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  const uploadFile = async (file, sessionId) => {
    // Untuk file kecil (<= 30MB), upload langsung tanpa chunking
    if (file.size <= CHUNK_SIZE) {
      return await uploadSmallFile(file, sessionId);
    } else {
      // Untuk file besar (> 30MB), gunakan chunking
      return await uploadLargeFile(file, sessionId);
    }
  };

  const uploadSmallFile = async (file, sessionId) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("sessionId", sessionId);
    // Ini adalah kunci perbaikannya: untuk file kecil, kita perlu menandainya sebagai file lengkap
    // bukan sebagai chunk
    formData.append("start", 0);
    formData.append("total_size", file.size);
    formData.append("filename", file.name);
    formData.append("is_small_file", "true");  // Menambahkan flag untuk menandai file kecil
  
    console.log(`Uploading small file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)}MB)`);

     // Update progress to show started
  setFileProgress((prevProgress) => ({
    ...prevProgress,
    [file.name]: 10,
  }));

  const response = await fetch("http://localhost:5001/upload-chunk", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload file failed: ${response.statusText}`);
  }

  const result = await response.json();
  console.log(`File upload response:`, result);

  // Update progress to 100% when complete
  setFileProgress((prevProgress) => ({
    ...prevProgress,
    [file.name]: 100,
  }));

  return result;
};

  const uploadLargeFile = async (file, sessionId) => {
    console.log(`Processing large file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)}MB)`);
    
    let start = 0;
    while (start < file.size) {
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);
      
      await uploadChunk(file, start, chunk, sessionId);
      start = end;
    }

    // Ensure progress shows 100% when all chunks are uploaded
    setFileProgress((prevProgress) => ({
      ...prevProgress,
      [file.name]: 100,
    }));
    
    console.log(`Completed uploading file: ${file.name}`);
    return { message: "Large file uploaded successfully" };
  };

  const uploadChunk = async (file, start, chunk, sessionId) => {
    const formData = new FormData();
    formData.append("file", chunk);
    formData.append("sessionId", sessionId);
    formData.append("start", start);
    formData.append("total_size", file.size);
    formData.append("filename", file.name);

    console.log(`Uploading chunk for ${file.name}: ${start}-${start + chunk.size} of ${file.size}`);

    const response = await fetch("http://localhost:5001/upload-chunk", {
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
      [file.name]: progress,
    }));

    return result;
  };

  const analyzeFilesWithGemini = async (savedFiles, uploadFolder) => {
    setIsAnalyzing(true);
    console.log("Starting Gemini analysis for files:", savedFiles);
  
    try {
      // Initialize analysis progress for each file
      const initialProgress = {};
      savedFiles.forEach((filePath) => {
        const fileName = filePath.split("/").pop();
        initialProgress[fileName] = 0;
      });
      setAnalysisProgress(initialProgress);
  
      const analysisResponse = await fetch("http://localhost:5001/analyze-files", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          files: savedFiles,
          folder: uploadFolder,
          analysisPrompt:
            "Analyze this code and identify any security vulnerabilities, hardcoded credentials, or sensitive data. Also suggest improvements for code quality and performance. Structure your response with clear sections for issues found and recommendations.",
        }),
      });
  
      const analysisResult = await analysisResponse.json();
      
      // Check if there are any errors in the response
      if (!analysisResponse.ok) {
        throw new Error(analysisResult.error || "Failed to analyze files");
      }
      
      // Even if response is 200, check if there were partial errors
      if (analysisResult.has_errors) {
        // Collect error messages
        const errorMessages = analysisResult.error_files.map(
          (file) => `${file.filename}: ${file.error}`
        ).join("\n");
        
        console.warn("Some files failed to analyze:", errorMessages);
        
        // Show warning to user about partial success
        alert(`Analysis partially completed with errors:\n${errorMessages}`);
      } else {
        console.log("Analysis completed successfully:", analysisResult);
        alert("Analysis complete! You can now view the results.");
      }
  
      setUploadStatus((prev) => ({
        ...prev,
        analyzed: true,
        analysisResults: analysisResult.analyzed_files || [],
        errorFiles: analysisResult.error_files || []
      }));
  
    } catch (error) {
      console.error("Analysis error:", error);
      
      // Set specific error status in application state
      setUploadStatus((prev) => ({
        ...prev,
        analyzed: false,
        analysisError: error.message
      }));
      
      // Show detailed error to user
      alert("Error analyzing files: " + error.message);
    } finally {
      setIsAnalyzing(false);
    }
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
      // Reset progress tracking
      const initialProgress = {};
      selectedFiles.forEach(file => {
        initialProgress[file.name] = 0;
      });
      setFileProgress(initialProgress);

      for (const file of selectedFiles) {
        // Menambahkan nomor baris pada file sebelum upload
        const fileWithLineNumbers = await addLineNumbersToFile(file);
        
        // Upload file (using chunking for large files)
        const fileObject = new File([fileWithLineNumbers], file.name, { type: file.type });
        await uploadFile(fileObject, sessionId);
      }

      console.log("All files uploaded, finalizing...");
      const finalizeResponse = await fetch("http://localhost:5001/finalize-upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sessionId,
          files: selectedFiles.map((f) => ({
            filename: f.name,
            size: f.size,
          })),
        }),
      });

      if (!finalizeResponse.ok) throw new Error("Failed to finalize upload");

      const result = await finalizeResponse.json();
      console.log("Upload finalized:", result);

      setUploadStatus((prevStatus) => ({
        ...prevStatus,
        uploaded: true,
        analyzed: false,
        message: result.message,
        analysisResults: [],
      }));

      setIsUploading(false); // Pastikan upload status dihentikan
      setIsAnalyzing(true); // Set analyzing status

      alert("Upload berhasil! Now starting analysis...");

      // Start analyzing files with Gemini after upload completes
      await analyzeFilesWithGemini(result.saved_files, result.folder);
    } catch (error) {
      console.error("Upload error:", error);
      setUploadStatus({
        uploaded: false,
        analyzed: false,
        message: error.message,
      });
      alert("Error: " + error.message);
    } finally {
      setIsUploading(false);
    }
  };


  // Fungsi untuk menampilkan ukuran file dalam format yang sesuai
  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + " B";
    else if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
    else return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  };
  

  return (
    <div className="container-homepage">
      <nav className="navbar">HauntAI</nav>
      <div className="help-icon-wrapper">
        <span
          className="help-icon blue"
          onClick={() => setShowGlobalTooltip(!showGlobalTooltip)}
          title="Click for upload guidelines"
        >
          ❓
        </span>

        {showGlobalTooltip && (
          <div className="tooltip-box-left">
            <p><strong>Upload Guidelines:</strong></p>
            <ul>
              <li>- For best results, make sure the total number of filtered files does not exceed 50.</li>
              <li>- If you upload more than 30 files, the chance of false positives will be higher.</li>
              <li><strong>For Website Setup:</strong></li>
                <ul>
                  <li>- Obtain your API key from <a href="https://aistudio.google.com/apikey" target="_blank">https://aistudio.google.com/apikey</a>.</li>
                  <li>- Update the API key in the file `index.py` at line 393.</li>
                </ul>
              <li><strong>CLI Setup:</strong></li>
                <ul>
                  <li>- Obtain your API key from <a href="https://aistudio.google.com/apikey" target="_blank">https://aistudio.google.com/apikey</a>.</li>
                  <li>- Update the API key in the file `cli.py` at line 44.</li>
                </ul>
            </ul>
          </div>
        )}
      </div>
      <div className="upload-container">
        <h2>Upload File or Folder</h2>
        <p className="upload-limit">HauntAI</p>
        <div className="upload-options">
          <div className="upload-box">
            <label className={`upload-label ${folderUploaded ? "disabled" : ""}`} >
              Upload File
              <input type="file" multiple onChange={handleFileUpload} disabled={folderUploaded} />
            </label>
          </div>
          <div className="upload-box">
            <label className={`upload-label ${fileUploaded ? "disabled" : ""}`} >
              Upload Folder
              <input type="file" webkitdirectory="" directory="" multiple onChange={handleFolderUpload} disabled={fileUploaded} />
            </label>
          </div>
        </div>
        <button className="upload-button" onClick={handleUploadToBackend} disabled={isUploading || isAnalyzing}>
          {isUploading ? "Uploading..." : isAnalyzing ? "Analyzing with AI..." : "Upload"}
        </button>
      </div>

      {selectedFiles.length > 0 && (
        <div className="folder-content-container">
          <h3>File yang Akan Diupload:</h3>
          <p className="total-files-info">Total selected files: {selectedFiles.length}</p>
          <ul className="file-list">
            {selectedFiles.map((file, index) => (
              <li key={index} className="file-item">
                <div className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">({formatFileSize(file.size)})</span>
                  {file.size > CHUNK_SIZE && <span className="chunking-indicator"></span>}
                </div>
                
                {isUploading && fileProgress[file.name] !== undefined && (
                  <div className="progress-container">
                    <div 
                      className="progress-bar" 
                      style={{ width: `${fileProgress[file.name]}%` }}
                    ></div>
                    <span className="progress-text">{fileProgress[file.name]}%</span>
                  </div>
                )}
                
                {isAnalyzing && analysisProgress[file.name] !== undefined && (
                  <span className="analyzing-indicator">Analyzing...</span>
                )}

              {uploadStatus.analyzed && uploadStatus.analysisResults.includes(file.name) && (
                <button
                onClick={() => window.open(`http://localhost:5001/view-pdf?filename=${file.name}`, '_blank')}
                className="download-button"
                >
                View PDF
                </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
