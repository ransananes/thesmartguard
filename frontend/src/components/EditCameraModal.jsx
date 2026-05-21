import React, { useState, useEffect } from 'react';
import { X, ChevronDown, ChevronUp } from 'lucide-react';

const EditCameraModal = ({ isOpen, onClose, onSave, camera }) => {
    const [name, setName] = useState('');
    const [streamUrl, setStreamUrl] = useState('');
    const [location, setLocation] = useState('');
    const [robotHost, setRobotHost] = useState('');
    const [robotPort, setRobotPort] = useState('');
    const [showRobotSection, setShowRobotSection] = useState(false);
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (camera) {
            setName(camera.name || '');
            setStreamUrl(camera.streamUrl || '');
            setLocation(camera.location || '');
            setRobotHost(camera.robotHost || '');
            setRobotPort(camera.robotPort ? String(camera.robotPort) : '');
            setShowRobotSection(!!(camera.robotHost));
            setError('');
        }
    }, [camera]);

    if (!isOpen || !camera) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await onSave(camera.id, {
                name: name.trim(),
                stream_url: streamUrl.trim(),
                location: location.trim() || null,
                robot_host: robotHost.trim() || null,
                robot_port: robotPort ? parseInt(robotPort) : null,
            });
            onClose();
        } catch (err) {
            setError(err.message || 'Failed to update camera');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl w-full max-w-md p-6 shadow-2xl">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-xl font-bold text-white">Edit Camera</h2>
                    <button onClick={onClose} className="text-neutral-400 hover:text-white transition-colors">
                        <X size={24} />
                    </button>
                </div>

                {error && (
                    <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-2 rounded-lg mb-4 text-sm">
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-neutral-400 mb-1">Camera Name</label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            required
                            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition-all"
                            placeholder="e.g. Front Door"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-neutral-400 mb-1">Stream URL</label>
                        <input
                            type="text"
                            value={streamUrl}
                            onChange={(e) => setStreamUrl(e.target.value)}
                            required
                            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition-all font-mono text-sm"
                            placeholder="rtsp://... or http://..."
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-neutral-400 mb-1">Location (Optional)</label>
                        <input
                            type="text"
                            value={location}
                            onChange={(e) => setLocation(e.target.value)}
                            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition-all"
                            placeholder="e.g. Living Room"
                        />
                    </div>

                    {/* Robot Camera (optional) */}
                    <div className="border border-white/5 rounded-lg overflow-hidden">
                        <button
                            type="button"
                            onClick={() => setShowRobotSection(v => !v)}
                            className="w-full flex items-center justify-between px-3 py-2.5 text-sm font-medium text-neutral-400 hover:text-white hover:bg-neutral-800/50 transition-colors"
                        >
                            <span>Robot Camera <span className="text-neutral-600 font-normal">(optional)</span></span>
                            {showRobotSection ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                        {showRobotSection && (
                            <div className="px-3 pb-3 pt-1 space-y-3 bg-neutral-800/20">
                                <div className="grid grid-cols-3 gap-3">
                                    <div className="col-span-2">
                                        <label className="block text-xs font-medium text-neutral-500 mb-1">Robot IP Address</label>
                                        <input
                                            type="text"
                                            value={robotHost}
                                            onChange={(e) => setRobotHost(e.target.value)}
                                            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition-all"
                                            placeholder="e.g. 192.168.1.64"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-neutral-500 mb-1">Cam Port</label>
                                        <input
                                            type="number"
                                            value={robotPort}
                                            onChange={(e) => setRobotPort(e.target.value)}
                                            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition-all"
                                            placeholder="81"
                                        />
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="flex justify-end gap-3 mt-6">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-300 hover:text-white hover:bg-neutral-800 transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="px-4 py-2 rounded-lg text-sm font-medium bg-purple-600 hover:bg-purple-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {isLoading ? 'Saving...' : 'Save Changes'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default EditCameraModal;
