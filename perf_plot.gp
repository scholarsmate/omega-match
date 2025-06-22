# perf_plot.gp (Dark Mode)
set datafile separator comma

set terminal pngcairo size 1600,900 enhanced font 'Verdana,12'
set output 'perf_results.png'

# Dark mode styling
set object 1 rectangle from screen 0,0 to screen 1,1 fillcolor rgb "black" behind
set border lc rgb "white"
set tics textcolor rgb "white"
set title textcolor rgb "white"
set xlabel textcolor rgb "white"
set ylabel textcolor rgb "white"
set key textcolor rgb "white"
set grid lc rgb "gray"

set title "OMG Match vs grep Performance (Release Build)"
set xlabel "Test Case"
set ylabel "Throughput (MB/sec)"

set style data histogram
set style histogram clustered gap 1
set style fill solid 1.00 border -1
set boxwidth 0.8
set grid ytics

set xtics rotate by -45

# Plot Release MB/s and Grep MB/s
plot 'perf_results.csv' using 4:xtic(1) title 'OMG Match Release MB/s' lc rgb "skyblue", \
     '' using 5 title 'grep MB/s' lc rgb "orange"
