import React, { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import VideoPlayer from '../components/VideoPlayer';
import VideoLoading from '../components/VideoLoading';
import Header from '../components/Header';
import StatCard from '../components/StatCard';
import RecognizedFaces from '../components/RecognizedFaces';
import RecentActivity from '../components/RecentActivity';
import RobotControl from '../components/RobotControl';
import AddCameraModal from '../components/AddCameraModal';
import EditCameraModal from '../components/EditCameraModal';
import SettingsModal from '../components/SettingsModal';
import { SYSTEM_STATUS } from '../constants';
import { api } from '../services/api';
import { Activity, Users, AlertTriangle, Lock, Plus, Trash2, Pencil, Camera, Settings, GripVertical, Bot } from 'lucide-react';

const StatusMonitor = () => {
    const [status, setStatus] = useState(SYSTEM_STATUS.SCANNING);
    const [cameras, setCameras] = useState([]);
    const [selectedCamera, setSelectedCamera] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    const [isAddCameraModalOpen, setIsAddCameraModalOpen] = useState(false);
    const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);

    const [statsData, setStatsData] = useState({ detections: 0, alerts: 0, active_cameras: 0 });
    const [sidebarTab, setSidebarTab] = useState('faces');


    const [showRobotPiP, setShowRobotPiP] = useState(false);
    const [robotCameraFeedUrl, setRobotCameraFeedUrl] = useState(null);

    const [editingCamera, setEditingCamera] = useState(null);

    const [draggedId, setDraggedId] = useState(null);
    const [dragOverId, setDragOverId] = useState(null);

    const applySavedOrder = (list) => {
        try {
            const saved = JSON.parse(localStorage.getItem('cameraOrder') || '[]');
            if (!saved.length) return list;
            return [...list].sort((a, b) => {
                const ai = saved.indexOf(a.id);
                const bi = saved.indexOf(b.id);
                return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
            });
        } catch {
            return list;
        }
    };

    const handleDragStart = (e, id) => {
        setDraggedId(id);
        e.dataTransfer.effectAllowed = 'move';
    };

    const handleDragOver = (e, id) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (id !== draggedId) setDragOverId(id);
    };

    const handleDrop = (e, targetId) => {
        e.preventDefault();
        if (!draggedId || draggedId === targetId) return;
        setCameras(prev => {
            const next = [...prev];
            const from = next.findIndex(c => c.id === draggedId);
            const to = next.findIndex(c => c.id === targetId);
            next.splice(to, 0, next.splice(from, 1)[0]);
            localStorage.setItem('cameraOrder', JSON.stringify(next.map(c => c.id)));
            return next;
        });
        setDraggedId(null);
        setDragOverId(null);
    };

    const handleDragEnd = () => {
        setDraggedId(null);
        setDragOverId(null);
    };


    const loadData = async () => {
        setIsLoading(true);
        try {
            const [camerasData, statsResponse] = await Promise.all([
                api.fetchCameras(),
                api.fetchStats()
            ]);

            if (camerasData.cameras && camerasData.cameras.length > 0) {
                const ordered = applySavedOrder(camerasData.cameras);
                setCameras(ordered);
                if (!selectedCamera) {
                    setSelectedCamera(ordered[0]);
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

    const handleEditCamera = async (cameraId, data) => {
        const response = await api.updateCamera(cameraId, data);
        await loadData();
        if (selectedCamera?.id === cameraId && response.camera) {
            setSelectedCamera(response.camera);
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





    // Poll robot status to get camera feed URL when robot is connected
    useEffect(() => {
        const fetchRobotStatus = async () => {
            try {
                const res = await api.robot.getStatus();
                if (res.success && res.status?.camera_feed_url) {
                    setRobotCameraFeedUrl('http://localhost:5000' + res.status.camera_feed_url);
                } else {
                    setRobotCameraFeedUrl(null);
                    setShowRobotPiP(false);
                }
            } catch (_) {}
        };
        fetchRobotStatus();
        const id = setInterval(fetchRobotStatus, 10000);
        return () => clearInterval(id);
    }, []);

    // Unknown-person notification: poll live_status every 5 s and fire a
    // browser notification + toast when a new persistent-unknown alert arrives.
    const lastAlertCountRef = useRef(null);
    useEffect(() => {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }

        const checkAlerts = async () => {
            try {
                const data = await api.fetchLiveStatus();
                const count = data.unknown_alert_count ?? 0;

                if (lastAlertCountRef.current !== null && count > lastAlertCountRef.current) {
                    toast.error('Unknown person detected for over 5 seconds!', {
                        duration: 8000,
                        icon: '⚠️',
                    });
                    if ('Notification' in window && Notification.permission === 'granted') {
                        new Notification('SmartGuard Security Alert', {
                            body: 'An unidentified person has been present for over 5 seconds.',
                            icon: '/favicon.ico',
                        });
                    }
                }

                lastAlertCountRef.current = count;
            } catch (_) {}
        };

        checkAlerts();
        const id = setInterval(checkAlerts, 5000);
        return () => clearInterval(id);
    }, []);

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
                                    pipUrl={robotCameraFeedUrl}
                                    showPip={showRobotPiP && !!robotCameraFeedUrl}
                                    onClosePip={() => setShowRobotPiP(false)}
                                />
                            </div>
                        ) : (
                            <VideoLoading />
                        )}


                        <div className="flex items-center gap-4">
                            <div className="flex gap-2 overflow-x-auto py-2 scrollbar-none flex-1">
                                {cameras.map(cam => (
                                    <div
                                        key={cam.id}
                                        draggable
                                        onDragStart={(e) => handleDragStart(e, cam.id)}
                                        onDragOver={(e) => handleDragOver(e, cam.id)}
                                        onDrop={(e) => handleDrop(e, cam.id)}
                                        onDragEnd={handleDragEnd}
                                        className={`relative group flex-shrink-0 transition-all duration-150 rounded-xl
                                            ${draggedId === cam.id ? 'opacity-30 scale-95' : 'opacity-100 scale-100'}
                                            ${dragOverId === cam.id && draggedId !== cam.id ? 'ring-2 ring-purple-500' : ''}
                                        `}
                                    >
                                        <button
                                            onClick={() => {
                                                setSelectedCamera(cam);
                                                if (cam.robotHost) {
                                                    const port = cam.robotPort || 81;
                                                    setRobotCameraFeedUrl(`http://localhost:5000/api/robot/camera_feed?host=${cam.robotHost}&port=${port}`);
                                                    setShowRobotPiP(true);
                                                }
                                            }}
                                            className={`pl-6 pr-16 py-2 rounded-xl text-sm font-semibold transition-all duration-300 border cursor-grab active:cursor-grabbing ${selectedCamera?.id === cam.id ? 'bg-purple-600/20 border-purple-500 text-purple-300 shadow-[0_0_15px_rgba(139,92,246,0.2)]' : 'bg-neutral-900/50 border-white/5 text-neutral-400 hover:text-white hover:border-white/10'}`}
                                        >
                                            {cam.name}
                                        </button>
                                        <GripVertical
                                            size={12}
                                            className="absolute left-1.5 top-1/2 -translate-y-1/2 text-neutral-600 opacity-0 group-hover:opacity-100 pointer-events-none"
                                        />
                                        <button
                                            draggable={false}
                                            onClick={(e) => { e.stopPropagation(); setEditingCamera(cam); }}
                                            className="absolute right-8 top-1/2 -translate-y-1/2 p-1.5 text-neutral-500 hover:text-purple-400 rounded-lg hover:bg-purple-500/10 transition-all opacity-0 group-hover:opacity-100"
                                            title="Edit Camera"
                                        >
                                            <Pencil size={14} />
                                        </button>
                                        <button
                                            draggable={false}
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

                                {robotCameraFeedUrl && (
                                    <button
                                        onClick={() => setShowRobotPiP(v => !v)}
                                        className={`p-2.5 rounded-lg transition-colors ${
                                            showRobotPiP
                                                ? 'bg-purple-600/20 text-purple-400 border border-purple-500/40'
                                                : 'hover:bg-neutral-800 text-neutral-400 hover:text-white'
                                        }`}
                                        title="Toggle Robot Camera"
                                    >
                                        <Bot size={20} />
                                    </button>
                                )}
                            </div>
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

                <EditCameraModal
                    isOpen={!!editingCamera}
                    onClose={() => setEditingCamera(null)}
                    onSave={handleEditCamera}
                    camera={editingCamera}
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
