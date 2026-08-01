import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { analyzeComplexity, generatePipeline } from '../utils/complexityAnalyzer';
import AgentCards from './AgentCards';
import ActivityConsole from './ActivityConsole';
import ProcessingTimeline from './ProcessingTimeline';
import { TbSparkles } from 'react-icons/tb';

export default function AIProcessingScreen({ query, isBackendFinished, onComplete }) {
  const [pipeline, setPipeline] = useState([]);
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [isSimulating, setIsSimulating] = useState(true);
  
  useEffect(() => {
    // 1. Determine complexity and generate pipeline
    const { targetDurationMs, level } = analyzeComplexity(query);
    const generatedPipeline = generatePipeline(level, targetDurationMs);
    setPipeline(generatedPipeline);
    
    // 2. Start the progression engine
    let currentStageIndex = 0;
    let accumulatedTime = 0;
    
    // We update the progress bar smoothly (e.g. 60fps)
    const startTime = Date.now();
    const progressInterval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(99, Math.floor((elapsed / targetDurationMs) * 100)); // Cap at 99% until complete
      setProgress(pct);
    }, 50);

    // Stage progression logic
    const advanceStage = () => {
      if (currentStageIndex >= generatedPipeline.length - 1) {
        setIsSimulating(false);
        clearInterval(progressInterval);
        return;
      }
      
      const currentStage = generatedPipeline[currentStageIndex];
      
      setTimeout(() => {
        currentStageIndex++;
        setActiveStageIndex(currentStageIndex);
        advanceStage();
      }, currentStage.durationMs);
    };

    advanceStage();

    return () => {
      clearInterval(progressInterval);
    };
  }, [query]);

  // 3. Coordinate completion: Wait for both simulation to finish AND backend to finish
  useEffect(() => {
    if (!isSimulating && isBackendFinished) {
      setProgress(100);
      setTimeout(() => {
        onComplete();
      }, 1000); // Give 1s for the 100% and checkmark animation to play
    }
  }, [isSimulating, isBackendFinished, onComplete]);

  const activeStageName = pipeline[activeStageIndex]?.name || '';

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="w-full max-w-5xl mx-auto panel-card relative overflow-hidden min-h-[500px]"
    >
      {/* Background glow effects */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-[#9C4A2A]/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-[#B8965A]/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 p-8 flex flex-col h-full">
        
        {/* Header */}
        <div className="flex items-center justify-between mb-8 pb-6 border-b border-black/10 dark:border-white/10">
          <div className="flex items-center gap-4">
            <div className="relative flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-900 border border-zinc-700 shadow-lg">
              <TbSparkles className="w-6 h-6 text-[#9C4A2A]" />
              {isSimulating && (
                <motion.div 
                  className="absolute inset-0 border border-[#9C4A2A] rounded-xl"
                  animate={{ scale: [1, 1.2, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              )}
            </div>
            <div>
              <h2 className="text-xl font-semibold text-zinc-100">AI Intelligent Processing</h2>
              <p className="text-sm text-zinc-400 mt-1 line-clamp-1 max-w-md">"{query}"</p>
            </div>
          </div>
          
          <div className="text-right">
            <div className="text-3xl font-light text-zinc-100">{progress}%</div>
            <div className="text-xs text-zinc-500 uppercase tracking-widest mt-1">Completing Analysis</div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1">
          
          {/* Left Column: Agents and Timeline */}
          <div className="col-span-1 lg:col-span-7 flex flex-col gap-8">
            <AgentCards activeStageName={activeStageName} />
            <div className="flex-1 min-h-[300px]">
              <ProcessingTimeline pipeline={pipeline} activeStageIndex={activeStageIndex} />
            </div>
          </div>

          {/* Right Column: Console */}
          <div className="col-span-1 lg:col-span-5 flex flex-col h-[450px]">
            <ActivityConsole isActive={true} backendFinished={isBackendFinished} />
          </div>

        </div>

        {/* Completion Overlay */}
        <AnimatePresence>
          {progress === 100 && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="absolute inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm"
            >
              <motion.div 
                initial={{ scale: 0.8, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                className="flex flex-col items-center"
              >
                <div className="w-20 h-20 bg-emerald-500/20 rounded-full flex items-center justify-center mb-6">
                  <TbSparkles className="w-10 h-10 text-emerald-400" />
                </div>
                <h2 className="text-3xl font-light text-white mb-2">Analysis Complete</h2>
                <p className="text-zinc-400">Rendering final dashboard...</p>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </motion.div>
  );
}
