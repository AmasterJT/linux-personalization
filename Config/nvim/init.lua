local install_path = vim.fn.stdpath('data') .. '/site/autoload/plug.vim'
if vim.fn.empty(vim.fn.glob(install_path)) > 0 then
  vim.fn.system({
    'curl', '-fLo', install_path, '--create-dirs',
    'https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim',
  })
  vim.cmd('autocmd VimEnter * PlugInstall --sync | source $MYVIMRC')
end

-- ::instalacion de plugins::

-- Configuración de vim-plug
vim.cmd([[
  call plug#begin('~/.vim/plugged')
  Plug 'tanvirtin/monokai.nvim'
  Plug 'joshdick/onedark.vim'
  Plug 'Yggdroot/indentLine'
  Plug 'mattn/emmet-vim'
  Plug 'preservim/nerdtree'
  Plug 'jiangmiao/auto-pairs'
  Plug 'neoclide/coc.nvim', {'branch': 'release'}
  Plug 'terryma/vim-multiple-cursors'
  Plug 'ryanoasis/vim-devicons'
  Plug 'junegunn/fzf', { 'do': { -> fzf#install() } }
  Plug 'junegunn/fzf.vim'
  Plug 'mhinz/vim-signify'
  Plug 'supermaven-inc/supermaven-nvim'
  call plug#end()
]])

-- ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

-- Atajos de edición solicitados, usando el portapapeles del sistema.
vim.keymap.set('x', '<C-c>', '"+y', { silent = true, desc = 'Copiar' })
vim.keymap.set('x', '<C-x>', '"+x', { silent = true, desc = 'Cortar' })
vim.keymap.set('n', '<C-v>', '"+p', { silent = true, desc = 'Pegar' })
vim.keymap.set('x', '<C-v>', '"+p', { silent = true, desc = 'Pegar reemplazando selección' })
vim.keymap.set('i', '<C-v>', '<C-r>+', { silent = true, desc = 'Pegar' })
vim.keymap.set('c', '<C-v>', '<C-r>+', { silent = true, desc = 'Pegar' })
vim.keymap.set('n', '<C-z>', 'u', { silent = true, desc = 'Deshacer' })
vim.keymap.set('i', '<C-z>', '<C-o>u', { silent = true, desc = 'Deshacer' })
vim.keymap.set('n', '<C-y>', '<C-r>', { silent = true, desc = 'Rehacer' })
vim.keymap.set('i', '<C-y>', '<C-o><C-r>', { silent = true, desc = 'Rehacer' })

-- CONFIGURACIONES BASICAS 
vim.opt.number = true              -- muestra los numeros de cada linea en la parte izquierda 
vim.opt.relativenumber = true      -- la distribucion de los numeros en lineas de manera relativa
vim.opt.mouse = 'a'                -- permite la interaccion con el mouse
vim.opt.showmode = true            -- comportamiento estándar: mostrar el modo actual
vim.cmd('syntax enable')           -- activa el coloreado de sintaxis en algunos tipos de archivos como html, c, c++
vim.opt.encoding = 'utf-8'         -- permite setear la codificación de archivos para aceptar caracteres especiales
vim.opt.shiftwidth = 4             -- la indentación genera 4 espacios
vim.opt.wrap = false               -- el texto en una linea no baja a la siguiente, solo continua en la misma hasta el infinito.
vim.opt.scrolloff = 2              -- mantener la línea activa separada de la barra inferior
vim.opt.swapfile = false           -- para evitar el mensaje que sale al abrir algunos archivos sobre swap.
vim.opt.clipboard = 'unnamedplus'  -- compartir el portapapeles del sistema

-- configuracion del tema
vim.opt.termguicolors = true       -- activa el true color en la terminal

-- Verificar si el esquema de colores 'monokai' está disponible antes de activarlo
local colorscheme = 'monokai_pro'
local ok, _ = pcall(vim.cmd, 'colorscheme ' .. colorscheme)
if not ok then
  vim.cmd('colorscheme onedark')
end

-- Fondo transparente conservando los colores y atributos del tema. Airline
-- permanece desactivado para evitar las copias móviles de su barra.
local transparent_groups = {
  'Normal', 'NormalNC', 'NormalFloat', 'FloatBorder', 'SignColumn',
  'LineNr', 'CursorLineNr', 'EndOfBuffer', 'VertSplit', 'WinSeparator',
  'StatusLine', 'StatusLineNC', 'TabLine', 'TabLineFill', 'TabLineSel',
  'Pmenu', 'PmenuSel', 'PmenuSbar', 'PmenuThumb', 'FoldColumn',
}

local function apply_transparency()
  for _, group in ipairs(transparent_groups) do
    local highlight = vim.api.nvim_get_hl(0, { name = group, link = false })
    if next(highlight) ~= nil then
      highlight.bg = nil
      highlight.ctermbg = nil
      vim.api.nvim_set_hl(0, group, highlight)
    end
  end
end

apply_transparency()
local appearance_group = vim.api.nvim_create_augroup('TransparentAppearance', { clear = true })
vim.api.nvim_create_autocmd('ColorScheme', {
  group = appearance_group,
  callback = apply_transparency,
})

-- Barra de estado nativa, inspirada en Airline pero sin su motor de redibujado.
-- Todos los grupos conservan el fondo transparente para evitar la franja gris.
local statusline_modes = {
  n = { 'NORMAL', 'NativeModeNormal' },
  i = { 'INSERT', 'NativeModeInsert' },
  v = { 'VISUAL', 'NativeModeVisual' },
  V = { 'V-LINE', 'NativeModeVisual' },
  ['\22'] = { 'V-BLOCK', 'NativeModeVisual' },
  s = { 'SELECT', 'NativeModeVisual' },
  S = { 'S-LINE', 'NativeModeVisual' },
  R = { 'REPLACE', 'NativeModeReplace' },
  c = { 'COMMAND', 'NativeModeCommand' },
  t = { 'TERMINAL', 'NativeModeTerminal' },
}

local function apply_statusline_theme()
  local groups = {
    NativeModeNormal = { fg = '#50fa7b', bold = true },
    NativeModeInsert = { fg = '#8be9fd', bold = true },
    NativeModeVisual = { fg = '#bd93f9', bold = true },
    NativeModeReplace = { fg = '#ff5555', bold = true },
    NativeModeCommand = { fg = '#f1fa8c', bold = true },
    NativeModeTerminal = { fg = '#ff79c6', bold = true },
    NativeStatusText = { fg = '#f8f8f2' },
    NativeStatusDim = { fg = '#6272a4' },
    NativeStatusAccent = { fg = '#50fa7b', bold = true },
    NativeStatusModified = { fg = '#ffb86c', bold = true },
    NativeStatusSeparator = { fg = '#6272a4' },
  }

  for group, highlight in pairs(groups) do
    vim.api.nvim_set_hl(0, group, highlight)
  end
end

apply_statusline_theme()
vim.api.nvim_create_autocmd('ColorScheme', {
  group = appearance_group,
  callback = apply_statusline_theme,
})

function _G.native_statusline()
  local mode = vim.api.nvim_get_mode().mode
  local mode_info = statusline_modes[mode] or statusline_modes[mode:sub(1, 1)] or statusline_modes.n

  return table.concat({
    '%#' .. mode_info[2] .. '#  ', mode_info[1], '  ',
    '%#NativeStatusSeparator#  ',
    '%#NativeStatusText#',
    '%{exists("*WebDevIconsGetFileTypeSymbol") ? WebDevIconsGetFileTypeSymbol() . " " : ""}',
    '%<%f',
    '%#NativeStatusModified#  %m%r',
    '%=',
    '%#NativeStatusDim#%{&filetype ==# "" ? "text" : &filetype}',
    '  │  %{&fileencoding ==# "" ? &encoding : &fileencoding}',
    '  │  ',
    '%#NativeStatusAccent#☰ %l/%L :%c  %p%%  ',
  })
end

vim.opt.showmode = false
vim.opt.statusline = '%!v:lua.native_statusline()'

-- ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

-- Autocompletado asistido. Sus teclas no interfieren con copiar, pegar,
-- deshacer ni rehacer.
require('supermaven-nvim').setup({
  keymaps = {
    accept_suggestion = '<C-l>',
    clear_suggestion = '<C-]>',
    accept_word = '<C-j>',
  },
})

-- configuracion de emmet-vim
vim.g.user_emmet_leader_key = ','  -- mapeando la tecla lider por una coma, con esto se completa los tag con doble coma.

-- configuracion de nerdtree
vim.api.nvim_set_keymap('n', '<C-t>', ':NERDTreeToggle<CR>', { noremap = true, silent = true })

-- configuracion por defecto de coc
-- TextEdit might fail if hidden is not set.
vim.opt.hidden = true

-- Deshabilitar advertencias de trailing spaces en CoC
vim.g.coc_status_error_sign = ''
vim.g.coc_status_warning_sign = ''

-- Some servers have issues with backup files, see #649.
vim.opt.backup = false
vim.opt.writebackup = false

-- Mantener los valores estándar de Neovim para una barra estable.
vim.opt.cmdheight = 1
vim.opt.laststatus = 2

-- Having longer updatetime (default is 4000 ms = 4 s) leads to noticeable
-- delays and poor user experience.
vim.opt.updatetime = 300

-- Don't pass messages to |ins-completion-menu|.
vim.opt.shortmess:append('c')

-- Always show the signcolumn, otherwise it would shift the text each time
-- diagnostics appear/become resolved.
if vim.fn.has('patch-8.1.1564') == 1 then
  -- Recently vim can merge signcolumn and number column into one
  vim.opt.signcolumn = 'number'
else
  vim.opt.signcolumn = 'yes'
end

-- Mapeos para CoC
vim.api.nvim_set_keymap('i', '<TAB>', [[pumvisible() ? "\<C-n>" : v:lua.check_back_space() ? "\<TAB>" : coc#refresh()]], { noremap = true, expr = true, silent = true })                                                                                              
vim.api.nvim_set_keymap('i', '<S-TAB>', [[pumvisible() ? "\<C-p>" : "\<C-h>"]], { noremap = true, expr = true, silent = true })

_G.check_back_space = function()
  local col = vim.fn.col('.') - 1
  return col == 0 or vim.fn.getline('.'):sub(col, col):match('%s') ~= nil
end

vim.api.nvim_set_keymap('i', '<c-space>', [[coc#refresh()]], { noremap = true, expr = true, silent = true })
vim.api.nvim_set_keymap('i', '<c-@>', [[coc#refresh()]], { noremap = true, expr = true, silent = true })

vim.api.nvim_set_keymap('i', '<cr>', [[pumvisible() ? coc#_select_confirm() : "\<C-g>u\<CR>\<c-r>=coc#on_enter()\<CR>"]], { noremap = true, expr = true, silent = true })                                                                                             

vim.api.nvim_set_keymap('n', '[g', '<Plug>(coc-diagnostic-prev)', { silent = true })
vim.api.nvim_set_keymap('n', ']g', '<Plug>(coc-diagnostic-next)', { silent = true })

vim.api.nvim_set_keymap('n', 'gd', '<Plug>(coc-definition)', { silent = true })
vim.api.nvim_set_keymap('n', 'gy', '<Plug>(coc-type-definition)', { silent = true })
vim.api.nvim_set_keymap('n', 'gi', '<Plug>(coc-implementation)', { silent = true })
vim.api.nvim_set_keymap('n', 'gr', '<Plug>(coc-references)', { silent = true })

vim.api.nvim_set_keymap('n', 'K', ':lua _G.show_documentation()<CR>', { silent = true })

_G.show_documentation = function()
  if vim.tbl_contains({'vim', 'help'}, vim.bo.filetype) then
    vim.cmd('h ' .. vim.fn.expand('<cword>'))
  elseif vim.fn['coc#rpc#ready']() then
    vim.fn.CocActionAsync('doHover')
  else
    vim.cmd('!' .. vim.o.keywordprg .. ' ' .. vim.fn.expand('<cword>'))
  end
end

vim.cmd('autocmd CursorHold * silent call CocActionAsync("highlight")')

vim.api.nvim_set_keymap('n', '<leader>rn', '<Plug>(coc-rename)', { silent = true })
vim.api.nvim_set_keymap('x', '<leader>f', '<Plug>(coc-format-selected)', { silent = true })
vim.api.nvim_set_keymap('n', '<leader>f', '<Plug>(coc-format-selected)', { silent = true })

vim.cmd([[
augroup mygroup
  autocmd!
  autocmd FileType typescript,json setl formatexpr=CocAction('formatSelected')
  autocmd User CocJumpPlaceholder call CocActionAsync('showSignatureHelp')
augroup end
]])

vim.api.nvim_set_keymap('x', '<leader>a', '<Plug>(coc-codeaction-selected)', { silent = true })
vim.api.nvim_set_keymap('n', '<leader>a', '<Plug>(coc-codeaction-selected)', { silent = true })
vim.api.nvim_set_keymap('n', '<leader>ac', '<Plug>(coc-codeaction)', { silent = true })
vim.api.nvim_set_keymap('n', '<leader>qf', '<Plug>(coc-fix-current)', { silent = true })

vim.api.nvim_set_keymap('x', 'if', '<Plug>(coc-funcobj-i)', { silent = true })
vim.api.nvim_set_keymap('o', 'if', '<Plug>(coc-funcobj-i)', { silent = true })
vim.api.nvim_set_keymap('x', 'af', '<Plug>(coc-funcobj-a)', { silent = true })
vim.api.nvim_set_keymap('o', 'af', '<Plug>(coc-funcobj-a)', { silent = true })

vim.api.nvim_set_keymap('x', 'ic', '<Plug>(coc-classobj-i)', { silent = true })
vim.api.nvim_set_keymap('o', 'ic', '<Plug>(coc-classobj-i)', { silent = true })
vim.api.nvim_set_keymap('x', 'ac', '<Plug>(coc-classobj-a)', { silent = true })
vim.api.nvim_set_keymap('o', 'ac', '<Plug>(coc-classobj-a)', { silent = true })

vim.api.nvim_set_keymap('n', '<leader>cl', ':CocCommand clangd.switchSourceHeader<CR>', { noremap = true, silent = true })

vim.api.nvim_set_keymap('n', '<C-f>', [[coc#float#has_scroll() ? coc#float#scroll(1) : "\<C-f>"]], { noremap = true, expr = true, silent = true })                                                                                                                    
vim.api.nvim_set_keymap('n', '<C-b>', [[coc#float#has_scroll() ? coc#float#scroll(0) : "\<C-b>"]], { noremap = true, expr = true, silent = true })                                                                                                                    
vim.api.nvim_set_keymap('i', '<C-f>', [[coc#float#has_scroll() ? "\<C-r>=coc#float#scroll(1)\<CR>" : "\<Right>"]], { noremap = true, expr = true, silent = true })                                                                                                    
vim.api.nvim_set_keymap('i', '<C-b>', [[coc#float#has_scroll() ? "\<C-r>=coc#float#scroll(0)\<CR>" : "\<Left>"]], { noremap = true, expr = true, silent = true })                                                                                                     
vim.api.nvim_set_keymap('v', '<C-f>', [[coc#float#has_scroll() ? coc#float#scroll(1) : "\<C-f>"]], { noremap = true, expr = true, silent = true })                                                                                                                    
vim.api.nvim_set_keymap('v', '<C-b>', [[coc#float#has_scroll() ? coc#float#scroll(0) : "\<C-b>"]], { noremap = true, expr = true, silent = true })                                                                                                                    

vim.api.nvim_set_keymap('n', '<C-s>', ':<C-u>CocList -I symbols<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>a', ':<C-u>CocList diagnostics<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>e', ':<C-u>CocList extensions<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>c', ':<C-u>CocList commands<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>o', ':<C-u>CocList outline<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>s', ':<C-u>CocList -I symbols<cr>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>j', ':<C-u>CocNext<CR>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>k', ':<C-u>CocPrev<CR>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('n', '<space>p', ':<C-u>CocListResume<CR>', { noremap = true, silent = true })

-- Abrir/Cerrar NERDTree con Ctrl + E.
vim.api.nvim_set_keymap('n', '<C-E>', ':NERDTreeToggle<CR>', { noremap = true, silent = true })
vim.api.nvim_set_keymap('i', '<C-E>', '<Esc>:NERDTreeToggle<CR>', { noremap = true, silent = true })
