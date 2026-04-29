import React, { useState, useEffect } from 'react';
import VideoPlayer from '../components/VideoPlayer';
import VideoLoading from '../components/VideoLoading';
import Header from '../components/Header';
import StatCard from '../components/StatCard';
import RecognizedFaces from '../components/RecognizedFaces';
import RecentActivity from '../components/RecentActivity';
import RobotControl from '../components/RobotControl';
import AddCameraModal from '../components/AddCameraModal';
import SettingsModal from '../components/SettingsModal';
import { SYSTEM_STATUS } from '../constants';
import { api } from '../services/api';
import { Activity, Users, AlertTriangle, Lock, Plus, Trash2, Camera, Settings } from 'lucide-react';

const StatusMonitor = () => {
    const [status, setStatus] = useState(SYSTEM_STATUS.SCANNING);
    const [cameras, setCameras] = useState([]);
    const [selectedCamera, setSelectedCamera] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    const [isAddCameraModalOpen, setIsAddCameraModalOpen] = useState(false);
    const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);

    const [statsData, setStatsData] = useState({ detections: 0, alerts: 0, active_cameras: 0 });
    const [sidebarTab, setSidebarTab] = useState('faces');

    const [autoFollow, setAutoFollow] = useState(false);
    const [knownOnly, setKnownOnly] = useState(false);
    const [followTarget, setFollowTarget] = useState(null);


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

        const intervalId = setInterval(() => {
            api.fetchStats().then(response => {
                if (response.stats) {
                    setStatsData(response.stats);
                }
            }).catch(e => console.error("Stats poll failed", e));
        }, 30000);

        return () => clearInterval(intervalId);
    }, []);


    const handleAddCamera = async (cameraData) => {
        try {
            const response = await api.addCamera(cameraData);
            await loadData();

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


    const handleFollowToggle = async () => {
        const newState = !autoFollow;
        try {
            const res = await api.robot.toggleFollow(newState, knownOnly);
            if (res.success) {
                setAutoFollow(newState);
                if (!newState) setFollowTarget(null);
            }
        } catch (e) {
            console.error('Follow toggle failed', e);
        }
    };

    const handleKnownOnlyChange = async (e) => {
        const checked = e.target.checked;
        setKnownOnly(checked);
        if (autoFollow) {
            await api.robot.toggleFollow(true, checked);
        }
    };


    useEffect(() => {
        if (!autoFollow) return;
        const id = setInterval(async () => {
            try {
                const res = await api.robot.getStatus();
                if (res.status?.follow_target !== undefined) {
                    setFollowTarget(res.status.follow_target);
                }
            } catch (_) { }
        }, 2000);
        return () => clearInterval(id);
    }, [autoFollow]);
    const stats = [
        { label: 'Active Cameras', value: statsData.active_cameras.toString(), icon: Activity },
        { label: 'Detections', value: statsData.detections.toString(), icon: Users },
        { label: 'Security Level', value: 'High', icon: Lock },
        { label: 'Alerts', value: statsData.alerts.toString(), icon: AlertTriangle },
    ];

    return (
        <div className="min-h-screen bg-neutral-950 text-white p-6 md:p-12 font-sans selection:bg-purple-500/30 relative overflow-hidden">
            {/* Background Effects */}
            <div className="absolute inset-0 bg-grid opacity-20 pointer-events-none" />
            <div className="absolute inset-0 bg-gradient-glow pointer-events-none" />
            <div className="scanline" />

            <div className="relative z-10">
                <Header />

                <main className="grid lg:grid-cols-3 gap-8">

                    <div className="lg:col-span-2 space-y-6">
                        {!isLoading && cameras.length === 0 ? (
                            <div className="w-full aspect-video glass-card flex flex-col items-center justify-center p-8 text-center space-y-6">
                                <div className="relative">
                                    <div className="absolute inset-0 bg-purple-500/20 blur-2xl rounded-full animate-pulse" />
                                    <div className="relative p-6 bg-purple-500/10 rounded-2xl border border-purple-500/20">
                                        <Camera size={48} className="text-purple-500" />
                                    </div>
                                </div>
                                <div>
                                    <h3 className="text-2xl font-bold text-white mb-2 tracking-tight">No Active Nodes Found</h3>
                                    <p className="text-neutral-400 max-w-sm mx-auto">
                                        Connect your security nodes to the centralized guard network.
                                    </p>
                                </div>
                                <button
                                    onClick={() => setIsAddCameraModalOpen(true)}
                                    className="btn-primary flex items-center gap-2 group"
                                >
                                    <Plus size={18} className="group-hover:rotate-90 transition-transform" />
                                    Initialize Camera
                                </button>
                            </div>
                        ) : selectedCamera ? (
                            <div className="glass-card overflow-hidden">
                                <VideoPlayer
                                    streamUrl={`http://localhost:5000/api/video_feed/${selectedCamera.id}`}
                                />
                            </div>
                        ) : (
                            <VideoLoading />
                        )}


                        <div className="flex items-center gap-4">
                            <div className="flex gap-2 overflow-x-auto py-2 scrollbar-none flex-1">
                                {cameras.map(cam => (
                                    <div key={cam.id} className="relative group flex-shrink-0">
                                        <button
                                            onClick={() => setSelectedCamera(cam)}
                                            className={`px-5 py-2 rounded-xl text-sm font-semibold transition-all duration-300 pr-10 border ${selectedCamera?.id === cam.id ? 'bg-purple-600/20 border-purple-500 text-purple-300 shadow-[0_0_15px_rgba(139,92,246,0.2)]' : 'bg-neutral-900/50 border-white/5 text-neutral-400 hover:text-white hover:border-white/10'}`}
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
                                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-neutral-500 hover:text-red-400 rounded-lg hover:bg-red-500/10 transition-all opacity-0 group-hover:opacity-100"
                                            title="Remove Camera"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                ))}
                            </div>

                            <div className="flex items-center gap-2 bg-neutral-900/50 p-1 rounded-xl border border-white/5">
                                <button
                                    onClick={() => setIsAddCameraModalOpen(true)}
                                    className="p-2.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition-colors"
                                    title="Add Camera"
                                >
                                    <Plus size={20} />
                                </button>

                                <button
                                    onClick={loadData}
                                    className="p-2.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition-colors"
                                    title="Refresh Stats"
                                >
                                    <Activity size={20} />
                                </button>

                                <button
                                    onClick={() => setIsSettingsModalOpen(true)}
                                    className="p-2.5 rounded-lg hover:bg-neutral-800 text-neutral-400 hover:text-white transition-colors"
                                    title="Notification Settings"
                                >
                                    <Settings size={20} />
                                </button>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 bg-neutral-900/50 rounded-xl border border-white/5 mt-3">

                            {/* Follow toggle button */}
                            <button
                                onClick={handleFollowToggle}
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all border ${autoFollow
                                        ? 'bg-purple-600/20 border-purple-500 text-purple-300 shadow-[0_0_12px_rgba(139,92,246,0.3)]'
                                        : 'border-white/10 text-neutral-400 hover:text-white hover:border-white/20'
                                    }`}
                            >
                                <span className={autoFollow ? 'animate-pulse' : ''}>🤖</span>
                                <span>{autoFollow ? 'Following...' : 'Auto Follow'}</span>
                            </button>

                            {/* Known only toggle */}
                            <label className="flex items-center gap-2 text-sm text-neutral-400 cursor-pointer select-none">
                                <input
                                    type="checkbox"
                                    checked={knownOnly}
                                    onChange={handleKnownOnlyChange}
                                    className="w-4 h-4 accent-purple-500 cursor-pointer"
                                />
                                Known faces only
                            </label>

                            {/* Live follow target indicator */}
                            {autoFollow && (
                                <div className="ml-auto flex items-center gap-2">
                                    {followTarget ? (
                                        <span className="px-3 py-1 rounded-full text-xs font-semibold bg-green-500/20 border border-green-500/40 text-green-300">
                                            👤 {followTarget}
                                        </span>
                                    ) : (
                                        <span className="px-3 py-1 rounded-full text-xs font-semibold bg-neutral-800 border border-white/5 text-neutral-500">
                                            Searching...
                                        </span>
                                    )}
                                </div>
                            )}
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


                    <div className="lg:col-span-1 flex flex-col h-[600px] glass-card overflow-hidden">

                        <div className="flex border-b border-white/5 p-1">
                            {['faces', 'history', 'robot'].map((tab) => (
                                <button
                                    key={tab}
                                    onClick={() => setSidebarTab(tab)}
                                    className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest transition-all duration-300 rounded-lg ${sidebarTab === tab
                                        ? 'bg-purple-600/20 text-purple-400 shadow-inner'
                                        : 'text-neutral-500 hover:text-neutral-300'
                                        }`}
                                >
                                    {tab}
                                </button>
                            ))}
                        </div>


                        <div className="flex-1 overflow-hidden relative">
                            {sidebarTab === 'faces' ? (
                                <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
                                    <RecognizedFaces />
                                </div>
                            ) : sidebarTab === 'history' ? (
                                <div className="absolute inset-0 overflow-y-auto p-4 custom-scrollbar">
                                    <RecentActivity />
                                </div>
                            ) : (
                                <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
                                    <RobotControl isActive={sidebarTab === 'robot'} />
                                </div>
                            )}
                        </div>
                    </div>
                </main>

                <AddCameraModal
                    isOpen={isAddCameraModalOpen}
                    onClose={() => setIsAddCameraModalOpen(false)}
                    onAdd={handleAddCamera}
                />

                <SettingsModal
                    isOpen={isSettingsModalOpen}
                    onClose={() => setIsSettingsModalOpen(false)}
                    onSave={loadData}
                />
            </div>
        </div>
    );
};

export default StatusMonitor;
