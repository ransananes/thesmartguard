import React, { useState, useEffect } from 'react';
import VideoPlayer from '../components/VideoPlayer';
import Header from '../components/Header';
import StatCard from '../components/StatCard';
import StatusIndicator from '../components/StatusIndicator';
import AddCameraModal from '../components/AddCameraModal';
import { SYSTEM_STATUS, MOCK_STREAM_URL } from '../constants';
import { api } from '../services/api';
import { Activity, Users, AlertTriangle, Lock, Plus, Trash2, Camera } from 'lucide-react';

const StatusMonitor = () => {
    const [status, setStatus] = useState(SYSTEM_STATUS.SCANNING);
    const [cameras, setCameras] = useState([]);
    const [selectedCamera, setSelectedCamera] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    const [isAddCameraModalOpen, setIsAddCameraModalOpen] = useState(false);

    const [statsData, setStatsData] = useState({ detections: 0, alerts: 0, active_cameras: 0 });

    // Fetch cameras and stats on mount
    const loadData = async () => {
        setIsLoading(true);
        try {
            const [camerasData, statsResponse] = await Promise.all([
                api.fetchCameras(),
                api.fetchStats()
            ]);

            if (camerasData.cameras && camerasData.cameras.length > 0) {
                setCameras(camerasData.cameras);
                if (!selectedCamera) {
                    setSelectedCamera(camerasData.cameras[0]);
                }
            } else {
                setCameras([]);
            }

            if (statsResponse.stats) {
                setStatsData(statsResponse.stats);
            }

        } catch (error) {
            console.error("Failed to load data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);


    const handleAddCamera = async (cameraData) => {
        try {
            const response = await api.addCamera(cameraData);
            await loadData(); // Refresh list and stats
            
            if (response.camera) {
                setSelectedCamera(response.camera);
            }
        } catch (error) {
            console.error("Failed to add camera:", error);
            alert("Failed to add camera: " + error.message);
        }
    };

    const handleDeleteCamera = async (cameraId) => {
        try {
            await api.deleteCamera(cameraId);
            await loadData();
            if (selectedCamera?.id === cameraId) {
                const remaining = cameras.filter(c => c.id !== cameraId);
                setSelectedCamera(remaining.length > 0 ? remaining[0] : null);
            }
        } catch (error) {
            console.error("Failed to delete camera:", error);
            alert("Failed to delete camera. Please try again.");
        }
    };

    const stats = [
        { label: 'Active Cameras', value: statsData.active_cameras.toString(), icon: Activity },
        { label: 'Detections', value: statsData.detections.toString(), icon: Users },
        { label: 'Security Level', value: 'High', icon: Lock },
        { label: 'Alerts', value: statsData.alerts.toString(), icon: AlertTriangle },
    ];

    return (
        <div className="min-h-screen bg-neutral-900 text-white p-6 md:p-12 font-sans selection:bg-purple-500/30">
            <Header />

            <main className="grid lg:grid-cols-3 gap-8">
                {/* Main Video Feed Area */}
                <div className="lg:col-span-2 space-y-6">
                    {!isLoading && cameras.length === 0 ? (
                        <div className="w-full aspect-video bg-neutral-900 rounded-xl border border-white/10 flex flex-col items-center justify-center p-8 text-center space-y-4">
                            <div className="relative">
                                <div className="absolute inset-0 bg-purple-500/20 blur-xl rounded-full animate-pulse" />
                                <Camera size={48} className="text-purple-500 relative z-10" />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold text-white mb-2">No Cameras Added</h3>
                                <p className="text-neutral-400 max-w-sm mx-auto">
                                    Connect your surveillance cameras to start monitoring your premises.
                                </p>
                            </div>
                            <button
                                onClick={() => setIsAddCameraModalOpen(true)}
                                className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors font-medium flex items-center gap-2"
                            >
                                <Plus size={18} />
                                Add Camera
                            </button>
                        </div>
                    ) : (
                        <VideoPlayer 
                            streamUrl={selectedCamera ? `http://localhost:5000/api/video_feed/${selectedCamera.id}` : MOCK_STREAM_URL} 
                        />
                    )}
                    
                    {/* Camera Selector */}
                    <div className="flex items-center gap-4">
                            <div className="flex gap-2 overflow-x-auto py-2 scrollbar-thin scrollbar-thumb-neutral-700 scrollbar-track-transparent flex-1">
                                 {cameras.map(cam => (
                                     <div key={cam.id} className="relative group">
                                         <button
                                            onClick={() => setSelectedCamera(cam)}
                                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap pr-8 ${selectedCamera?.id === cam.id ? 'bg-purple-600 text-white' : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'}`}
                                         >
                                             {cam.name}
                                         </button>
                                         <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (window.confirm(`Are you sure you want to remove the camera "${cam.name}"?`)) {
                                                    handleDeleteCamera(cam.id);
                                                }
                                            }}
                                            className="absolute right-1 top-1/2 -translate-y-1/2 p-1 text-neutral-400 hover:text-red-500 rounded-full hover:bg-neutral-700/50 transition-all opacity-0 group-hover:opacity-100"
                                            title="Remove Camera"
                                         >
                                             <Trash2 size={14} />
                                         </button>
                                     </div>
                                 ))}
                            </div>
                        <button
                            onClick={() => setIsAddCameraModalOpen(true)}
                            className="p-2 rounded-lg bg-neutral-800 text-neutral-400 hover:bg-neutral-700 hover:text-white transition-colors flex-shrink-0"
                            title="Add Camera"
                        >
                            <Plus size={20} />
                        </button>
                        
                        <button
                            onClick={loadData}
                            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg transition-colors font-medium text-sm"
                            title="Refresh Stats"
                        >
                            Refresh Stats
                        </button>
                    </div>
                    
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        {stats.map((stat, i) => (
                            <StatCard 
                                key={i}
                                label={stat.label}
                                value={stat.value}
                                icon={stat.icon}
                            />
                        ))}
                    </div>
                </div>

                {/* Status Sidebar */}
                <div className="lg:col-span-1">
                    <StatusIndicator status={status} />
                </div>
            </main>

            <AddCameraModal 
                isOpen={isAddCameraModalOpen} 
                onClose={() => setIsAddCameraModalOpen(false)} 
                onAdd={handleAddCamera} 
            />
        </div>
    );
};

export default StatusMonitor;
