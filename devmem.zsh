autoload -Uz add-zsh-hook
zmodload zsh/datetime

typeset -g _DM_SPOOL="${DEVMEM_SPOOL:-${XDG_STATE_HOME:-$HOME/.local/state}/devmem/spool}"
typeset -g _dm_cmd _dm_stat _dm_cwd

# owner only directory and file, created once at load time
() {
  local dir=${_DM_SPOOL:h}
  [[ -d $dir ]] || mkdir -p -m 700 "$dir" 2>/dev/null
  [[ -e $_DM_SPOOL ]] || (umask 077; : >> "$_DM_SPOOL") 2>/dev/null
}

_dm_preexec() {
    # skip commands that start with a space
    [[ $1 == [[:space:]]* ]] && { _dm_cmd=; return }

    _dm_cmd=$1
    _dm_start="$EPOCHREALTIME"
    _dm_cwd="$PWD"

}

_dm_precmd() {
    local exit_code=$?

    [[ -z $_dm_cmd ]] && return

    local c=$_dm_cmd
    _dm_cmd=""

    # clean text
    c=${c//\\/\\\\}     # backslash
    c=${c//$'\n'/\\n}   # newline
    c=${c//$'\t'/\\t}   # tab 
    

    local -i dur_ms=$(( (EPOCHREALTIME - _dm_start) * 1000 ))
    { print -r -- "$dur_ms"$'\t'"$exit_code"$'\t'"$_dm_cwd"$'\t'"$c" >> "$_DM_SPOOL" } 2>/dev/null
    
    return $exit_code

}

add-zsh-hook preexec _dm_preexec
add-zsh-hook precmd _dm_precmd