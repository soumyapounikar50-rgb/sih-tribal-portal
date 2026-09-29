import { useState, useRef, useCallback } from 'react';
import axios from 'axios';
import Webcam from 'react-webcam';
import './App.css';

// Helper function to convert Webcam Base64 image to a File object
const dataURLtoFile = (dataurl, filename) => {
  let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
  bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
  while(n--){
      u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, {type:mime});
}

function App() {
  // OCR State
  const [docFile, setDocFile] = useState(null);
  const [expectedName, setExpectedName] = useState("");
  const [docResult, setDocResult] = useState(null);
  const [docLoading, setDocLoading] = useState(false);

  // Face Match State
  const [idFile, setIdFile] = useState(null);
  const [webcamImg, setWebcamImg] = useState(null);
  const [faceResult, setFaceResult] = useState(null);
  const [faceLoading, setFaceLoading] = useState(false);
  
  const webcamRef = useRef(null);

  const capture = useCallback(() => {
    const imageSrc = webcamRef.current.getScreenshot();
    setWebcamImg(imageSrc);
  }, [webcamRef]);

  // Handle OCR Submission
  const handleVerifyDocument = async () => {
    if (!docFile || !expectedName) return alert("Please provide a name and document.");
    setDocLoading(true);
    
    const formData = new FormData();
    formData.append("expected_name", expectedName);
    formData.append("file", docFile);

    try {
      const response = await axios.post("http://localhost:8000/verify-document/", formData);
      setDocResult(response.data);
    } catch (error) {
      console.error(error);
      setDocResult({ error: "Failed to connect to AI Server" });
    }
    setDocLoading(false);
  };

  // Handle Face Match Submission
  const handleVerifyFace = async () => {
    if (!idFile || !webcamImg) return alert("Please provide an ID card and capture a selfie.");
    setFaceLoading(true);
    
    const selfieFile = dataURLtoFile(webcamImg, 'live_selfie.jpg');
    
    const formData = new FormData();
    formData.append("id_card", idFile);
    formData.append("live_selfie", selfieFile);

    try {
      const response = await axios.post("http://localhost:8000/verify-face/", formData);
      setFaceResult(response.data);
    } catch (error) {
      console.error(error);
      setFaceResult({ error: "Failed to connect to AI Server" });
    }
    setFaceLoading(false);
  };

  return (
    <div className="app-container">
      <header>
        <h1>Ministry of Tribal Affairs</h1>
        <p>SIH26239: AI-Enabled Scholarship Verification Portal</p>
      </header>

      <div className="dashboard">
        {/* Module 1: Document Verification */}
        <div className="card">
          <h2>1. Caste Document OCR</h2>
          <div className="input-group">
            <label>Applicant Full Name</label>
            <input 
              type="text" 
              placeholder="e.g. Rahul Kumar" 
              value={expectedName} 
              onChange={(e) => setExpectedName(e.target.value)} 
            />
          </div>
          <div className="input-group">
            <label>Upload Certificate Image</label>
            <input type="file" onChange={(e) => setDocFile(e.target.files[0])} accept="image/*" />
          </div>
          <button onClick={handleVerifyDocument} disabled={docLoading}>
            {docLoading ? "Scanning Document..." : "Verify Document"}
          </button>
          
          {docResult && (
            <div className="result-box">
              <h3>Result: {docResult.status}</h3>
              <p>Confidence: {docResult.confidence_score}%</p>
              <pre>{docResult.extracted_text}</pre>
            </div>
          )}
        </div>

        {/* Module 2: Facial Verification */}
        <div className="card">
          <h2>2. Live Biometric Match</h2>
          <div className="input-group">
            <label>Upload Aadhaar / ID Card</label>
            <input type="file" onChange={(e) => setIdFile(e.target.files[0])} accept="image/*" />
          </div>
          
          <div className="webcam-container">
            <label>Live Applicant Selfie</label>
            {webcamImg ? (
              <div>
                <img src={webcamImg} alt="Selfie" className="preview-img" />
                <button className="secondary-btn" onClick={() => setWebcamImg(null)}>Retake</button>
              </div>
            ) : (
              <div>
                <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" className="webcam" />
                <button className="capture-btn" onClick={capture}>Capture Photo</button>
              </div>
            )}
          </div>

          <button onClick={handleVerifyFace} disabled={faceLoading}>
            {faceLoading ? "Running Face Match..." : "Verify Identity"}
          </button>

          {faceResult && (
            <div className="result-box">
              <h3>Status: {faceResult.status}</h3>
              <p>Match: {faceResult.is_match ? "✅ True" : "❌ False"}</p>
              <p>Similarity Distance: {faceResult.similarity_distance}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;