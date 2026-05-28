import React, { useState, useEffect } from 'react';
import { Camera, Upload, Trash2, UserPlus, Loader2 } from 'lucide-react';
import { api } from '../services/api';
import toast from 'react-hot-toast';

const RecognizedFaces = () => {
    const [activeTab, setActiveTab] = useState('live');
    const [faces, setFaces] = useState([]);
    const [newFaceName, setNewFaceName] = useState('');
    const [uploadFile, setUploadFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [deletingId, setDeletingId] = useState(null);
    const [recentDetections, setRecentDetections] = useState([]);

    useEffect(() => {
        loadFaces();
    }, []);

    const fetchDetections = async () => {
        try {
            const data = await api.getRecentDetections();
            if (data && data.detections) {
                setRecentDetections(data.detections);
            }
        } catch (e) {
            console.error("Poll failed", e);
        }
    };

    useEffect(() => {
        if (activeTab === 'live') {
            fetchDetections();
            const interval = setInterval(fetchDetections, 2000);
            return () => clearInterval(interval);
        }
    }, [activeTab]);

    const loadFaces = async () => {
        try {
            const result = await api.getFaces();
            if (result.success) {
                setFaces(result.faces);
            }
        } catch (error) {
            console.error("Failed to load faces", error);
        }
    };

    const handleUpload = async (e) => {
        e.preventDefault();
        if (!uploadFile || !newFaceName) return;

        setIsUploading(true);
        const formData = new FormData();
        formData.append('image', uploadFile);
        formData.append('name', newFaceName);

        try {
            await api.addFace(formData);
            setNewFaceName('');
            setUploadFile(null);
            await loadFaces();
            toast.success('Face added successfully!');
        } catch (error) {
            console.error("Error adding face", error);
            toast.error('Failed to add face. ' + (error.message || ''));
        } finally {
            setIsUploading(false);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Are you sure?')) return;
        
        setDeletingId(id);
        try {
            await api.deleteFace(id);
            await loadFaces();
            toast.success('Face deleted.');
        } catch (error) {
            console.error("Error deleting face", error);
            toast.error('Failed to delete face.');
        } finally {
            setDeletingId(null);
        }
    };

    return (
        <div className="h-full flex flex-col">

            <div className="flex border-b border-neutral-800">
                <button
                    onClick={() => setActiveTab('live')}
                    className={`flex-1 py-4 text-sm font-medium transition-colors ${
                        activeTab === 'live' 
                        ? 'bg-neutral-800 text-purple-400 border-b-2 border-purple-500' 
                        : 'text-neutral-400 hover:text-white'
                    }`}
                >
                    Live Recognition
                </button>
                <button
                    onClick={() => setActiveTab('manage')}
                    className={`flex-1 py-4 text-sm font-medium transition-colors ${
                        activeTab === 'manage' 
                        ? 'bg-neutral-800 text-purple-400 border-b-2 border-purple-500' 
                        : 'text-neutral-400 hover:text-white'
                    }`}
                >
                    Manage Faces
                </button>
            </div>


            <div className="flex-1 overflow-y-auto p-4">
                {activeTab === 'live' ? (
                    <div className="space-y-4">
                             <div className="flex justify-between items-center">
                                 <h4 className="text-xs font-bold text-neutral-400 uppercase tracking-widest pl-1">Recent Detections</h4>
                                 <button onClick={fetchDetections} className="text-xs text-purple-400 hover:text-purple-300">Refresh</button>
                             </div>
                             
                             {recentDetections.length === 0 ? (
                                 <div className="text-center p-4 border border-dashed border-neutral-800 rounded-lg text-neutral-600 text-sm">
                                     No detections yet
                                 </div>
                             ) : (
                                 recentDetections.map((det, i) => {
                                     const name = det.label.replace('Face: ', '');
                                     const isUnknown = name === 'Unknown';
                                     
                                     return (
                                        <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border ${isUnknown ? 'bg-red-900/10 border-red-900/30' : 'bg-green-900/10 border-green-900/30'}`}>

                                            {det.image_path ? (
                                                <img 
                                                    src={`http://localhost:5000${det.image_path}`} 
                                                    alt={name}
                                                    className="w-12 h-12 rounded-lg object-cover border border-neutral-700"
                                                />
                                            ) : (
                                                <div className={`w-12 h-12 rounded-lg flex items-center justify-center font-bold text-lg ${isUnknown ? 'bg-red-500/20 text-red-500' : 'bg-green-500/20 text-green-500'}`}>
                                                    {name.charAt(0)}
                                                </div>
                                            )}
                                            
                                            <div className="flex-1 min-w-0">
                                                <div className="flex justify-between items-start">
                                                    <p className={`font-medium truncate ${isUnknown ? 'text-red-200' : 'text-green-200'}`}>{name}</p>
                                                    <span className="text-xs text-neutral-500 whitespace-nowrap">
                                                        {new Date(/[Z+]/.test(det.timestamp) ? det.timestamp : det.timestamp + 'Z').toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', timeZone: 'Asia/Jerusalem'})}
                                                    </span>
                                                </div>
                                                <p className="text-xs text-neutral-500 mt-1 capitalize">{det.label}</p>
                                                
                                                {isUnknown && (
                                                    <button
                                                        onClick={() => {
                                                            const newName = window.prompt("Enter name for this person:");
                                                            if (newName) {
                                                                const toastId = toast.loading('Adding face...');
                                                                api.addFaceFromDetection(det.id, newName)
                                                                    .then((res) => {
                                                                        const msg = res.cleaned_up ? ` & removed ${res.cleaned_up} duplicates.` : '.';
                                                                        toast.success('Face added' + msg, { id: toastId });
                                                                        loadFaces();
                                                                        fetchDetections();
                                                                    })
                                                                    .catch(err => {
                                                                        toast.error('Failed: ' + err.message, { id: toastId });
                                                                    });
                                                            }
                                                        }}
                                                        className="mt-2 text-xs bg-red-500/20 hover:bg-red-500/30 text-red-300 px-2 py-1 rounded border border-red-500/30 transition-colors flex items-center gap-1"
                                                    >
                                                        <UserPlus size={12} /> Add to Known
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                     );
                                 })
                             )}
                    </div>
                ) : (
                    <div className="space-y-6">
                        <form onSubmit={handleUpload} className="bg-neutral-800/50 p-4 rounded-xl space-y-4">
                            <h3 className="text-white font-medium flex items-center gap-2">
                                <UserPlus size={18} /> Add New Face
                            </h3>
                            <input
                                type="text"
                                placeholder="Name (e.g., John Doe)"
                                value={newFaceName}
                                onChange={(e) => setNewFaceName(e.target.value)}
                                className="w-full bg-black/50 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                                required
                            />
                            <div className="border-2 border-dashed border-neutral-700 rounded-lg p-4 text-center hover:border-purple-500 transition-colors cursor-pointer relative">
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={(e) => setUploadFile(e.target.files[0])}
                                    className="absolute inset-0 opacity-0 cursor-pointer"
                                    required
                                />
                                <Upload className="w-6 h-6 mx-auto mb-2 text-neutral-400" />
                                <span className="text-sm text-neutral-400">
                                    {uploadFile ? uploadFile.name : "Upload Photo"}
                                </span>
                            </div>
                            <button
                                type="submit"
                                disabled={isUploading}
                                className={`w-full py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 ${
                                    isUploading 
                                    ? 'bg-neutral-700 cursor-not-allowed text-neutral-400'
                                    : 'bg-purple-600 hover:bg-purple-700 text-white'
                                }`}
                            >
                                {isUploading ? <Loader2 className="animate-spin w-5 h-5" /> : null}
                                {isUploading ? 'Adding...' : 'Add Face'}
                            </button>
                        </form>


                        <div className="space-y-2">
                            <h3 className="text-neutral-400 text-sm uppercase tracking-wider font-bold">Known People ({faces.length})</h3>
                            {faces.length === 0 && (
                                <p className="text-neutral-600 text-sm">No known faces yet.</p>
                            )}
                            {faces.map(face => (
                                <div key={face.id} className="flex items-center justify-between bg-neutral-800/30 p-3 rounded-lg border border-neutral-800">
                                    <div className="flex items-center gap-3">
                                        {face.image_url ? (
                                            <img 
                                                src={`http://localhost:5000${face.image_url}`} 
                                                alt={face.name}
                                                className="w-10 h-10 rounded-full object-cover border border-purple-900/50"
                                            />
                                        ) : (
                                            <div className="w-10 h-10 rounded-full bg-purple-900/50 flex items-center justify-center text-purple-300 font-bold text-xs">
                                                {face.name.charAt(0)}
                                            </div>
                                        )}
                                        <span className="text-white font-medium">{face.name}</span>
                                    </div>
                                    <button
                                        onClick={() => handleDelete(face.id)}
                                        disabled={deletingId === face.id}
                                        className="text-neutral-500 hover:text-red-500 transition-colors p-2 hover:bg-neutral-800 rounded-full disabled:opacity-50"
                                        title="Delete Face"
                                    >
                                        {deletingId === face.id ? (
                                             <Loader2 className="animate-spin w-4 h-4" />
                                        ) : (
                                             <Trash2 size={16} />
                                        )}
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RecognizedFaces;
