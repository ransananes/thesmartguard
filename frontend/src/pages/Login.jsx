import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Lock, User, AlertCircle, ChevronRight, CheckCircle2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../services/api';

const Login = ({ onLogin }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await new Promise(r => setTimeout(r, 800));
            
            const data = await api.login(username, password);
            if (data.success) {
                setSuccess(true);
                localStorage.setItem('isAuthenticated', 'true');
                localStorage.setItem('token', data.token);
                localStorage.setItem('user', JSON.stringify(data.user));
                
                if (onLogin) onLogin();


                setTimeout(() => {
                    navigate('/dashboard');
                }, 1000);
            } else {
                setError(data.message || 'Login failed');
                setIsLoading(false);
            }
        } catch (err) {
            setError(err.message || 'Connection failed.');
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#05050A] text-white flex items-center justify-center p-4 overflow-hidden relative">

            <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0">
                <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-purple-900/20 rounded-full blur-[120px]" />
                <div className="absolute bottom-[-10%] right-[-10%] w-[500px] h-[500px] bg-blue-900/20 rounded-full blur-[120px]" />
            </div>


            <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 z-0 pointer-events-none" />
            <div className="absolute inset-0 z-0 opacity-10" 
                style={{backgroundImage: 'radial-gradient(circle at 1px 1px, white 1px, transparent 0)', backgroundSize: '40px 40px'}}>
            </div>

            <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
                className="w-full max-w-md relative z-10"
            >
                <div className="bg-black/40 backdrop-blur-2xl p-8 rounded-3xl border border-white/10 shadow-2xl relative overflow-hidden group">
                    
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-purple-500 to-transparent opacity-50 animate-scan" />
                    
                    <div className="flex flex-col items-center mb-10 relative">
                        <motion.div 
                            initial={{ y: -20, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.2 }}
                            className="w-20 h-20 bg-gradient-to-br from-purple-500/20 to-blue-500/10 rounded-2xl flex items-center justify-center mb-6 border border-white/5 shadow-inner"
                        >
                            <Shield className="w-10 h-10 text-purple-400 drop-shadow-[0_0_15px_rgba(168,85,247,0.5)]" />
                        </motion.div>
                        <motion.h1 
                            initial={{ y: -10, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.3 }}
                            className="text-3xl font-bold tracking-tight text-center bg-clip-text text-transparent bg-gradient-to-r from-white via-white to-white/50"
                        >
                            CLASSIFIED ACCESS
                        </motion.h1>
                        <motion.p 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.4 }}
                            className="text-blue-200/40 text-sm mt-2 font-mono uppercase tracking-[0.2em]"
                        >
                            The Smart Guard System
                        </motion.p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6 relative">
                        <AnimatePresence>
                            {error && (
                                <motion.div 
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden"
                                >
                                    <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
                                        <AlertCircle size={18} />
                                        <span>{error}</span>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        <div className="space-y-4">
                            <div className="group/input relative">
                                <label className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest pl-1 mb-1 block group-focus-within/input:text-purple-400 transition-colors">Operative ID</label>
                                <div className="relative">
                                    <User className="absolute left-4 top-3.5 text-neutral-500 w-5 h-5 group-focus-within/input:text-purple-400 transition-colors" />
                                    <input
                                        type="text"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        className="w-full bg-neutral-900/50 border border-white/10 rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:border-purple-500/50 focus:bg-purple-900/10 transition-all text-sm placeholder:text-neutral-700 font-mono"
                                        placeholder="USERNAME"
                                    />
                                </div>
                            </div>

                            <div className="group/input relative">
                                <label className="text-[10px] font-bold text-neutral-500 uppercase tracking-widest pl-1 mb-1 block group-focus-within/input:text-purple-400 transition-colors">Security Key</label>
                                <div className="relative">
                                    <Lock className="absolute left-4 top-3.5 text-neutral-500 w-5 h-5 group-focus-within/input:text-purple-400 transition-colors" />
                                    <input
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="w-full bg-neutral-900/50 border border-white/10 rounded-xl py-3 pl-12 pr-4 focus:outline-none focus:border-purple-500/50 focus:bg-purple-900/10 transition-all text-sm placeholder:text-neutral-700 font-mono"
                                        placeholder="PASSWORD"
                                    />
                                </div>
                            </div>
                        </div>

                        <motion.button
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            type="submit"
                            disabled={isLoading || success}
                            className={`w-full relative group overflow-hidden rounded-xl p-[1px] ${success ? 'cursor-default' : ''}`}
                        >
                            <div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl" />
                            <div className={`relative bg-neutral-900/90 w-full h-full rounded-xl py-3.5 flex items-center justify-center transition-all ${isLoading || success ? 'bg-transparent' : 'group-hover:bg-opacity-0'}`}>
                                {isLoading || success ? (
                                    <div className="flex items-center gap-2 text-white font-bold tracking-wide">
                                        {success ? (
                                            <>
                                                <CheckCircle2 className="w-5 h-5" />
                                                <span>ACCESS GRANTED</span>
                                            </>
                                        ) : (
                                            <>
                                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                <span>VERIFYING...</span>
                                            </>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2 text-white font-bold tracking-wide">
                                        <span>INITIATE SEQUENCE</span>
                                        <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                    </div>
                                )}
                            </div>
                        </motion.button>
                    </form>


                    <div className="mt-8 flex justify-between items-center opacity-30 text-[10px] font-mono border-t border-white/10 pt-4">
                        <span>SECURE CONNECTION</span>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

import PropTypes from 'prop-types';
Login.propTypes = {
  onLogin: PropTypes.func
};

export default Login;
