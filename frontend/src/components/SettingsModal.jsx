import React, { useState, useEffect } from 'react';
import { X, Bell, Save } from 'lucide-react';
import { api } from '../services/api';

const SettingsModal = ({ isOpen, onClose, onSave }) => {
    const [settings, setSettings] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (isOpen) {
            loadSettings();
        }
    }, [isOpen]);

    const loadSettings = async () => {
        setLoading(true);
        try {
            const data = await api.getSettings();
            if (data.success && data.settings) {
                setSettings(data.settings);
            }
        } catch (error) {
            console.error("Failed to load settings:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = (index) => {
        const newSettings = [...settings];
        newSettings[index].enabled = !newSettings[index].enabled;
        setSettings(newSettings);
    };

    const handleSave = async () => {
        try {
            await api.updateSettings(settings);
            if (onSave) onSave();
            onClose();
        } catch (error) {
            console.error("Failed to save settings:", error);
            alert("Failed to save settings");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
                <div className="flex items-center justify-between p-6 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-500/10 rounded-lg">
                            <Bell className="w-5 h-5 text-purple-500" />
                        </div>
                        <h2 className="text-xl font-bold">Notification Settings</h2>
                    </div>
                    <button onClick={onClose} className="text-neutral-400 hover:text-white transition-colors">
                        <X size={20} />
                    </button>
                </div>


                <div className="p-6 space-y-4">
                    <p className="text-sm text-neutral-400">
                        Customize which detection events trigger an alert.
                    </p>

                    {loading ? (
                        <div className="flex justify-center py-8">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {settings.map((setting, index) => (
                                <div key={index} className="flex items-center justify-between p-3 rounded-xl bg-neutral-800/50 hover:bg-neutral-800 transition-colors border border-white/5">
                                    <span className="font-medium capitalize">{setting.label.replace('Face: ', 'Face Detected: ')}</span>
                                    
                                    <button 
                                        onClick={() => handleToggle(index)}
                                        className={`w-12 h-6 rounded-full relative transition-colors duration-300 ${setting.enabled ? 'bg-purple-600' : 'bg-neutral-700'}`}
                                    >
                                        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform duration-300 ${setting.enabled ? 'left-7' : 'left-1'}`} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>


                <div className="p-6 border-t border-white/5 flex justify-end gap-3">
                    <button 
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
                    >
                        Cancel
                    </button>
                    <button 
                        onClick={handleSave}
                        className="px-4 py-2 bg-white text-black hover:bg-neutral-200 rounded-lg font-medium transition-colors flex items-center gap-2"
                    >
                        <Save size={18} />
                        Save Changes
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SettingsModal;
